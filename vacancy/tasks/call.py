import logging
from collections.abc import Iterable
from datetime import date, datetime, timedelta

import sentry_sdk
from celery import shared_task
from django.db import connection
from django.utils import timezone

from telegram.choices import CallStatus, CallType
from telegram.service.group import GroupService
from vacancy.choices import STATUS_ACTIVE, STATUS_APPROVED, STATUS_CLOSED, STATUS_SEARCH_STOPPED
from vacancy.models import Vacancy, VacancyUserCall
from vacancy.services.observers.events import (
    VACANCY_AFTER_START_CALL,
    VACANCY_BEFORE_CALL,
    VACANCY_CLOSE,
    VACANCY_CLOSE_PAYMENT_DOES_NOT_EXIST,
    VACANCY_START_CALL,
)
from vacancy.services.observers.subscriber_setup import telegram_notifier, vacancy_publisher

Minutes = int
logger = logging.getLogger(__name__)


def _send_rollcall_reminder(vacancy: Vacancy, call_type: CallType) -> None:
    """Send rollcall reminder to vacancy owner."""
    from telegram.handlers.bot_instance import bot
    from vacancy.services.call_markup import get_rollcall_reminder_markup

    text = "Підтвердіть явку робочих на роботу" if call_type == CallType.START else "Підтвердіть наявність робочих"
    try:
        bot.send_message(
            chat_id=vacancy.owner.id,
            text=text,
            reply_markup=get_rollcall_reminder_markup(vacancy, call_type),
        )
    except Exception as e:
        logger.warning(f"_send_rollcall_reminder: vacancy {vacancy.pk}: {e}")


def _escalate_rollcall(vacancy: Vacancy, call_label: str) -> None:
    """Notify admins and kick owner after max reminders exceeded."""
    from service.broadcast_service import TelegramBroadcastService

    owner = vacancy.owner
    admin_text = (
        f"⚠️ Немає підтвердження {call_label}\n"
        f"Вакансія: {vacancy.address}\n"
        f"Заказчик: {owner.full_name or str(owner.id)}\n"
        f"Телефон: {getattr(owner, 'phone_number', None) or '—'}"
    )
    try:
        broadcast = TelegramBroadcastService(notifier=telegram_notifier)
        broadcast.admin_broadcast(text=admin_text)
    except Exception as e:
        logger.warning(f"_escalate_rollcall ({call_label}): admin broadcast failed: {e}")

    if vacancy.group:
        try:
            GroupService.kick_user(chat_id=vacancy.group.id, user_id=owner.id)
        except Exception as e:
            logger.warning(f"_escalate_rollcall ({call_label}): kick owner failed: {e}")

        # Delete employer invite message from bot chat
        msg_id = vacancy.extra.get("employer_invite_msg_id")
        if msg_id:
            try:
                from telegram.handlers.bot_instance import bot

                bot.delete_message(chat_id=owner.id, message_id=msg_id)
            except Exception as e:
                logger.warning(f"_escalate_rollcall: delete invite msg failed: {e}")


def _update_channel_search_stopped(vacancy: Vacancy) -> None:
    """Edit channel message to 'Пошук завершено' (no join button)."""
    if not vacancy.channel:
        return
    try:
        from service.notifications import NotificationMethod
        from service.telegram_strategy_factory import TelegramStrategyFactory
        from telegram.handlers.bot_instance import bot
        from telegram.models import ChannelMessage
        from vacancy.services.vacancy_formatter import VacancyTelegramTextFormatter

        channel_message = (
            ChannelMessage.objects.filter(
                channel_id=vacancy.channel.id,
                extra__vacancy_id=vacancy.id,
            )
            .order_by("-id")
            .first()
        )
        if channel_message:
            text = VacancyTelegramTextFormatter(vacancy).for_channel(status="full")
            strategy = TelegramStrategyFactory.get_strategy(NotificationMethod.TEXT)
            strategy.update(bot, vacancy.channel.id, text=text, message_id=channel_message.message_id)
    except Exception as e:
        logger.warning(f"_update_channel_search_stopped: vacancy {vacancy.pk}: {e}")


def get_before_start_vacancies(delay: Minutes = 120) -> Iterable[Vacancy]:
    vacancies = Vacancy.objects.filter(
        status__in=[STATUS_ACTIVE, STATUS_APPROVED],
        date=date.today(),
    )

    naive_now = datetime.now()
    aware_now = timezone.make_aware(naive_now, timezone.get_current_timezone())
    filtered_vacancies = []
    for vacancy in vacancies:
        start_naive = datetime.combine(vacancy.date, vacancy.start_time)
        start_aware = timezone.make_aware(start_naive, timezone.get_current_timezone())

        before_start_time = start_aware - timedelta(minutes=delay)
        if before_start_time < aware_now < start_aware:
            filtered_vacancies.append(vacancy)
    return filtered_vacancies


def get_start_vacancies(delay: Minutes = 10) -> Iterable[Vacancy]:
    vacancies = Vacancy.objects.filter(
        status__in=[STATUS_ACTIVE, STATUS_APPROVED],
        date=date.today(),
    )

    naive_now = datetime.now()
    aware_now = timezone.make_aware(naive_now, timezone.get_current_timezone())
    filtered_vacancies = []
    for vacancy in vacancies:
        start_naive = datetime.combine(vacancy.date, vacancy.start_time)
        start_aware = timezone.make_aware(start_naive, timezone.get_current_timezone())

        after_start_time = start_aware + timedelta(minutes=delay)
        if after_start_time > aware_now > start_aware:
            filtered_vacancies.append(vacancy)
    return filtered_vacancies


def get_final_vacancies() -> Iterable[Vacancy]:
    vacancies = Vacancy.objects.filter(
        status__in=[STATUS_ACTIVE, STATUS_APPROVED],
        date=date.today(),
    )

    naive_now = datetime.now()
    aware_now = timezone.make_aware(naive_now, timezone.get_current_timezone())
    filtered_vacancies = []
    for vacancy in vacancies:
        end_naive = datetime.combine(vacancy.date, vacancy.end_time)
        end_aware = timezone.make_aware(end_naive, timezone.get_current_timezone())

        if aware_now > end_aware:
            filtered_vacancies.append(vacancy)
    return filtered_vacancies


def get_final_call_vacancies(before_end: Minutes = 60) -> Iterable[Vacancy]:
    """Vacancies where end_time is within `before_end` minutes from now (for final rollcall)."""
    vacancies = Vacancy.objects.filter(
        status__in=[STATUS_ACTIVE, STATUS_APPROVED],
        date=date.today(),
    )

    naive_now = datetime.now()
    aware_now = timezone.make_aware(naive_now, timezone.get_current_timezone())
    filtered_vacancies = []
    for vacancy in vacancies:
        end_naive = datetime.combine(vacancy.date, vacancy.end_time)
        end_aware = timezone.make_aware(end_naive, timezone.get_current_timezone())
        trigger_time = end_aware - timedelta(minutes=before_end)

        if aware_now > trigger_time and aware_now < end_aware:
            filtered_vacancies.append(vacancy)
    return filtered_vacancies


def before_start_call(vacancies: Iterable[Vacancy]):
    for vacancy in vacancies:
        vacancy_publisher.notify(VACANCY_BEFORE_CALL, data={"vacancy": vacancy})


def after_first_call_check(vacancies: Iterable[Vacancy], delay: Minutes = 20):
    for vacancy in vacancies:
        calls = VacancyUserCall.objects.filter(vacancy_user__in=vacancy.members, call_type=CallType.AFTER_START)
        for call in calls:
            if timezone.now() - call.created_at > timedelta(minutes=delay):
                if not call.status == CallStatus.CONFIRM:
                    try:
                        GroupService.kick_user(
                            chat_id=call.vacancy_user.vacancy.group.id,
                            user_id=call.vacancy_user.user.id,
                        )
                    except Exception:
                        sentry_sdk.capture_exception()


_REMINDER_INTERVAL = 300  # 5 minutes in seconds
_MAX_REMINDERS = 12


def start_call_check(vacancies: Iterable[Vacancy]):
    for vacancy in vacancies:
        sent_start_call = vacancy.extra.get("sent_start_call", False)

        if not sent_start_call:
            # Initial send
            vacancy_publisher.notify(VACANCY_START_CALL, data={"vacancy": vacancy})
            vacancy.extra["sent_start_call"] = True
            vacancy.extra["start_call_sent_at"] = timezone.now().timestamp()
            vacancy.extra["start_call_reminders"] = 0

            fields_to_save = ["extra"]
            if vacancy.search_active or vacancy.status == STATUS_APPROVED:
                vacancy.status = STATUS_SEARCH_STOPPED
                vacancy.search_active = False
                vacancy.search_stopped_at = timezone.now()
                fields_to_save += ["status", "search_active", "search_stopped_at"]
                _update_channel_search_stopped(vacancy)
            vacancy.save(update_fields=fields_to_save)

        elif not vacancy.first_rollcall_passed and not vacancy.extra.get("start_call_escalated"):
            elapsed = timezone.now().timestamp() - vacancy.extra.get("start_call_sent_at", 0)
            if elapsed < _REMINDER_INTERVAL:
                continue

            reminders = vacancy.extra.get("start_call_reminders", 0)
            if reminders >= _MAX_REMINDERS:
                _escalate_rollcall(vacancy, call_label="1 переклички")
                vacancy.extra["start_call_escalated"] = True
            else:
                _send_rollcall_reminder(vacancy, call_type=CallType.START)
                vacancy.extra["start_call_reminders"] = reminders + 1
                vacancy.extra["start_call_sent_at"] = timezone.now().timestamp()
            vacancy.save(update_fields=["extra"])


def final_call_check(vacancies: Iterable[Vacancy]):
    for vacancy in vacancies:
        sent_final_call = vacancy.extra.get("sent_final_call", False)

        if not sent_final_call:
            # Initial send
            vacancy_publisher.notify(VACANCY_AFTER_START_CALL, data={"vacancy": vacancy})
            vacancy.extra["sent_final_call"] = True
            vacancy.extra["final_call_sent_at"] = timezone.now().timestamp()
            vacancy.extra["final_call_reminders"] = 0
            vacancy.save(update_fields=["extra"])

        elif not vacancy.second_rollcall_passed and not vacancy.extra.get("final_call_escalated"):
            elapsed = timezone.now().timestamp() - vacancy.extra.get("final_call_sent_at", 0)
            if elapsed < _REMINDER_INTERVAL:
                continue

            reminders = vacancy.extra.get("final_call_reminders", 0)
            if reminders >= _MAX_REMINDERS:
                _escalate_rollcall(vacancy, call_label="2 переклички")
                vacancy.extra["final_call_escalated"] = True
            else:
                _send_rollcall_reminder(vacancy, call_type=CallType.AFTER_START)
                vacancy.extra["final_call_reminders"] = reminders + 1
                vacancy.extra["final_call_sent_at"] = timezone.now().timestamp()
            vacancy.save(update_fields=["extra"])


def close_vacancy(vacancy: Vacancy):
    if not vacancy.extra.get("payment_checked", False):
        if vacancy.extra.get("is_paid", False):
            vacancy_publisher.notify(VACANCY_CLOSE, data={"vacancy": vacancy})
        else:
            vacancy_publisher.notify(VACANCY_CLOSE_PAYMENT_DOES_NOT_EXIST, data={"vacancy": vacancy})

        vacancy.extra["payment_checked"] = True
        vacancy.save(update_fields=["extra"])


@shared_task
def before_start_call_task():
    logger.info("task_started", extra={"task": "before_start_call_task"})
    connection.close()
    vacancies = get_before_start_vacancies()
    before_start_call(vacancies=vacancies)
    logger.info("task_completed", extra={"task": "before_start_call_task", "processed": len(list(vacancies))})


@shared_task
def after_first_call_check_task(delay: Minutes = 20):
    logger.info("task_started", extra={"task": "after_first_call_check_task"})
    connection.close()
    vacancies = get_before_start_vacancies()
    after_first_call_check(vacancies=vacancies, delay=delay)
    logger.info("task_completed", extra={"task": "after_first_call_check_task", "processed": len(list(vacancies))})


@shared_task
def start_call_check_task():
    logger.info("task_started", extra={"task": "start_call_check_task"})
    connection.close()
    # Initial send: vacancies in the 0–10 min after start window
    start_call_check(vacancies=get_start_vacancies())
    # Reminder window: sent but unconfirmed (incl. SEARCH_STOPPED after auto-stop)
    # IMPORTANT: only pick vacancies where start_time has already passed!
    naive_now = datetime.now()
    aware_now = timezone.make_aware(naive_now, timezone.get_current_timezone())
    reminder_candidates = []
    for v in Vacancy.objects.filter(
        date=date.today(),
        status__in=[STATUS_ACTIVE, STATUS_APPROVED, STATUS_SEARCH_STOPPED],
        first_rollcall_passed=False,
    ):
        start_naive = datetime.combine(v.date, v.start_time)
        start_aware = timezone.make_aware(start_naive, timezone.get_current_timezone())
        if aware_now >= start_aware:
            reminder_candidates.append(v)
    start_call_check(vacancies=reminder_candidates)
    logger.info("task_completed", extra={"task": "start_call_check_task", "processed": None})


@shared_task
def final_call_check_task():
    logger.info("task_started", extra={"task": "final_call_check_task"})
    connection.close()
    # Initial send: ACTIVE/APPROVED vacancies 1h before end_time
    final_call_check(vacancies=get_final_call_vacancies())
    # Reminder window: SEARCH_STOPPED vacancies past end_time (auto-stopped at start)
    aware_now = timezone.make_aware(datetime.now(), timezone.get_current_timezone())
    stopped_candidates = []
    for v in Vacancy.objects.filter(
        date=date.today(),
        status=STATUS_SEARCH_STOPPED,
        second_rollcall_passed=False,
    ):
        end_aware = timezone.make_aware(datetime.combine(v.date, v.end_time), timezone.get_current_timezone())
        trigger_time = end_aware - timedelta(minutes=60)
        if aware_now > trigger_time:
            stopped_candidates.append(v)
    final_call_check(vacancies=stopped_candidates)
    logger.info("task_completed", extra={"task": "final_call_check_task", "processed": None})


@shared_task
def close_vacancy_task(delay: Minutes = 120):
    logger.info("task_started", extra={"task": "close_vacancy_task"})
    connection.close()
    vacancies = get_final_vacancies()
    processed = 0
    for vacancy in vacancies:
        if vacancy.closed_at is not None:
            continue  # already handled by close_lifecycle_timer_task
        if not vacancy.status == STATUS_CLOSED:
            end_naive = datetime.combine(vacancy.date, vacancy.end_time)
            end_time = timezone.make_aware(end_naive, timezone.get_current_timezone())
            if end_time + timedelta(minutes=delay) < timezone.now():
                close_vacancy(vacancy=vacancy)
                processed += 1
    logger.info("task_completed", extra={"task": "close_vacancy_task", "processed": processed})


@shared_task
def close_lifecycle_timer_task():
    """
    Runs every 30s. After 3 hours triggers full close (kick users, free group)
    for vacancies where employer pressed "Закрити" or stopped search.
    """
    logger.info("task_started", extra={"task": "close_lifecycle_timer_task"})
    connection.close()
    threshold = timezone.now() - timedelta(hours=3)

    # Case a: employer pressed "Закрити вакансію" — closed_at timer, group still attached
    for vacancy in Vacancy.objects.filter(
        closed_at__isnull=False,
        closed_at__lte=threshold,
        group__isnull=False,
    ):
        logger.info(f"close_lifecycle_timer_task: freeing group for vacancy {vacancy.pk} (closed_at timer)")
        vacancy_publisher.notify(VACANCY_CLOSE, data={"vacancy": vacancy})

    # Case b: employer stopped search — 3h passed with no manual close
    processed = 0
    for vacancy in Vacancy.objects.filter(
        search_stopped_at__isnull=False,
        search_stopped_at__lte=threshold,
        status=STATUS_SEARCH_STOPPED,
        closed_at__isnull=True,
    ):
        logger.info(f"close_lifecycle_timer_task: closing vacancy {vacancy.pk} (search_stopped_at timer)")
        vacancy_publisher.notify(VACANCY_CLOSE, data={"vacancy": vacancy})
        processed += 1
    # Case c: paid vacancies — 3h after payment, free group
    from payment.models import MonobankPayment

    paid_vacancies = Vacancy.objects.filter(
        status="paid",
        group__isnull=False,
    )

    for vacancy in paid_vacancies:
        last_payment = (
            MonobankPayment.objects.filter(
                vacancy=vacancy,
                status=MonobankPayment.Status.SUCCESS,
            )
            .order_by("-updated_at")
            .first()
        )
        if last_payment and last_payment.updated_at <= threshold:
            logger.info(f"close_lifecycle_timer_task: closing vacancy {vacancy.pk} (3h after payment)")
            vacancy_publisher.notify(VACANCY_CLOSE, data={"vacancy": vacancy})
            processed += 1

    logger.info("task_completed", extra={"task": "close_lifecycle_timer_task", "processed": processed})


@shared_task
def worker_join_confirm_check_task():
    """
    Runs every 30s. Reminds unconfirmed workers at minutes 1–4 after joining.
    Kicks and deactivates them after 5 minutes of no confirmation.
    """
    logger.info("task_started", extra={"task": "worker_join_confirm_check_task"})
    connection.close()
    from telegram.choices import CallStatus, CallType
    from telegram.handlers.bot_instance import bot
    from telegram.service.group import GroupService
    from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

    KICK_AFTER = 300  # 5 minutes in seconds
    REMIND_MINUTES = {1, 2, 3, 4}

    pending = VacancyUserCall.objects.filter(
        call_type=CallType.WORKER_JOIN_CONFIRM.value,
        status=CallStatus.SENT.value,
    ).select_related("vacancy_user__user", "vacancy_user__vacancy__group")

    for call in pending:
        elapsed = (timezone.now() - call.created_at).total_seconds()
        user = call.vacancy_user.user
        vacancy = call.vacancy_user.vacancy

        if elapsed >= KICK_AFTER:
            # Kick and deactivate
            if vacancy.group:
                try:
                    GroupService.kick_user(chat_id=vacancy.group.id, user_id=user.id)
                except Exception as e:
                    logger.warning(f"worker_join_confirm: kick failed for user {user.id}: {e}")
            call.status = CallStatus.REJECT.value
            call.save(update_fields=["status"])
            logger.info(f"worker_join_confirm: kicked user {user.id} (no confirm in 5 min)")
            continue

        # Reminder at minutes 1, 2, 3, 4 — only in first 30s of that minute
        elapsed_minute = int(elapsed // 60)
        in_reminder_window = (elapsed % 60) < 30
        if elapsed_minute in REMIND_MINUTES and in_reminder_window:
            try:
                bot.send_message(
                    chat_id=user.id,
                    text=CallVacancyTelegramTextFormatter(vacancy).worker_join_reminder(),
                )
            except Exception as e:
                logger.warning(f"worker_join_confirm: reminder failed for user {user.id}: {e}")
    logger.info("task_completed", extra={"task": "worker_join_confirm_check_task", "processed": None})


_RENEWAL_OFFER_INTERVAL = 1800  # 30 minutes in seconds
_RENEWAL_MAX_REMINDERS = 6  # 6 × 30 min = 3 hours

_RENEWAL_WORKER_INTERVAL = 300  # 5 minutes in seconds
_RENEWAL_WORKER_MAX_REMINDERS = 4


@shared_task
def renewal_offer_task():
    """
    Runs every 30s. Sends renewal offer to employer after payment.
    Repeats every 30 min up to 6 times (3 hours total).
    """
    logger.info("task_started", extra={"task": "renewal_offer_task"})
    connection.close()
    from django.db.models import Q

    from telegram.handlers.bot_instance import bot
    from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter
    from vacancy.services.call_markup import get_renewal_offer_markup

    candidates = (
        Vacancy.objects.filter(
            second_rollcall_passed=True,
            closed_at__isnull=True,
        )
        .filter(
            extra__is_paid=True,
        )
        .exclude(Q(extra__renewal_offered=True))
    )

    for vacancy in candidates:
        extra = vacancy.extra
        # Skip if employer already responded
        if extra.get("renewal_accepted") or extra.get("renewal_declined"):
            extra["renewal_offered"] = True
            vacancy.save(update_fields=["extra"])
            continue

        if not extra.get("renewal_started"):
            # Initial send
            try:
                bot.send_message(
                    chat_id=vacancy.owner.id,
                    text=CallVacancyTelegramTextFormatter(vacancy).renewal_offer(),
                    reply_markup=get_renewal_offer_markup(vacancy),
                )
            except Exception as e:
                logger.warning(f"renewal_offer_task: initial send failed for vacancy {vacancy.pk}: {e}")
                continue
            extra["renewal_started"] = True
            extra["renewal_sent_at"] = timezone.now().timestamp()
            extra["renewal_reminders"] = 0
            vacancy.save(update_fields=["extra"])

        elif not extra.get("renewal_expired"):
            elapsed = timezone.now().timestamp() - extra.get("renewal_sent_at", 0)
            if elapsed < _RENEWAL_OFFER_INTERVAL:
                continue

            reminders = extra.get("renewal_reminders", 0)
            if reminders >= _RENEWAL_MAX_REMINDERS:
                extra["renewal_expired"] = True
                extra["renewal_offered"] = True
                vacancy.save(update_fields=["extra"])
                logger.info(f"renewal_offer_task: offer expired for vacancy {vacancy.pk}")
            else:
                try:
                    bot.send_message(
                        chat_id=vacancy.owner.id,
                        text=CallVacancyTelegramTextFormatter(vacancy).renewal_offer(),
                        reply_markup=get_renewal_offer_markup(vacancy),
                    )
                except Exception as e:
                    logger.warning(f"renewal_offer_task: reminder failed for vacancy {vacancy.pk}: {e}")
                    continue
                extra["renewal_reminders"] = reminders + 1
                extra["renewal_sent_at"] = timezone.now().timestamp()
                vacancy.save(update_fields=["extra"])
    logger.info("task_completed", extra={"task": "renewal_offer_task", "processed": None})


@shared_task
def renewal_worker_check_task():
    """
    Runs every 30s. Reminds workers who haven't answered renewal poll.
    Kicks after 4 reminders (20 min). When all answered — compares count with people_count.
    """
    logger.info("task_started", extra={"task": "renewal_worker_check_task"})
    connection.close()
    from telegram.handlers.bot_instance import bot
    from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

    pending = VacancyUserCall.objects.filter(
        call_type=CallType.RENEWAL_WORKER.value,
        status=CallStatus.SENT.value,
    ).select_related("vacancy_user__user", "vacancy_user__vacancy__group", "vacancy_user__vacancy__owner")

    # Group by vacancy to detect "all answered" after kicks
    vacancy_ids_with_pending = set()

    for call in pending:
        elapsed = (timezone.now() - call.created_at).total_seconds()
        user = call.vacancy_user.user
        vacancy = call.vacancy_user.vacancy
        vacancy_ids_with_pending.add(vacancy.pk)

        if elapsed >= _RENEWAL_WORKER_INTERVAL * _RENEWAL_WORKER_MAX_REMINDERS:
            # Kick and mark reject
            if vacancy.group:
                try:
                    GroupService.kick_user(chat_id=vacancy.group.id, user_id=user.id)
                except Exception as e:
                    logger.warning(f"renewal_worker_check: kick failed for user {user.id}: {e}")
            call.status = CallStatus.REJECT.value
            call.save(update_fields=["status"])
            logger.info(f"renewal_worker_check: kicked user {user.id} (no renewal confirm in 20 min)")
            continue

        # Reminder every 5 min — only in the first 30s of that 5-min slot
        elapsed_slot = int(elapsed // _RENEWAL_WORKER_INTERVAL)
        in_window = (elapsed % _RENEWAL_WORKER_INTERVAL) < 30
        if elapsed_slot >= 1 and in_window:
            try:
                bot.send_message(
                    chat_id=user.id,
                    text=CallVacancyTelegramTextFormatter(vacancy).renewal_worker_reminder(),
                )
            except Exception as e:
                logger.warning(f"renewal_worker_check: reminder failed for user {user.id}: {e}")

    # Check vacancies where poll may have just completed (all responded)
    handled_vacancies = set()
    answered_vacancies = (
        VacancyUserCall.objects.filter(
            call_type=CallType.RENEWAL_WORKER.value,
        )
        .exclude(
            status=CallStatus.SENT.value,
        )
        .values_list("vacancy_user__vacancy_id", flat=True)
        .distinct()
    )

    for vacancy_id in answered_vacancies:
        if vacancy_id in vacancy_ids_with_pending:
            continue  # still has pending calls
        if vacancy_id in handled_vacancies:
            continue

        # Check if all renewal worker calls for this vacancy are settled
        still_pending = VacancyUserCall.objects.filter(
            call_type=CallType.RENEWAL_WORKER.value,
            status=CallStatus.SENT.value,
            vacancy_user__vacancy_id=vacancy_id,
        ).exists()
        if still_pending:
            continue

        vacancy = Vacancy.objects.filter(pk=vacancy_id).select_related("owner").first()
        if not vacancy:
            continue
        if vacancy.extra.get("renewal_worker_check_done"):
            continue

        confirmed_count = VacancyUserCall.objects.filter(
            call_type=CallType.RENEWAL_WORKER.value,
            status=CallStatus.CONFIRM.value,
            vacancy_user__vacancy_id=vacancy_id,
        ).count()

        needed = vacancy.people_count
        from telegram.handlers.bot_instance import bot
        from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

        if confirmed_count < needed:
            # Not enough workers — publish to channel to find more
            vacancy.search_active = True
            vacancy.extra["renewal_worker_check_done"] = True
            vacancy.save(update_fields=["search_active", "extra"])
            logger.info(
                f"renewal_worker_check: vacancy {vacancy.pk} needs more workers ({confirmed_count}/{needed}), search_active=True"
            )
        elif confirmed_count > needed:
            excess = confirmed_count - needed
            try:
                from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

                bot.send_message(
                    chat_id=vacancy.owner.id,
                    text=CallVacancyTelegramTextFormatter(vacancy).renewal_too_many_workers(excess),
                )
            except Exception as e:
                logger.warning(f"renewal_worker_check: employer notify failed for vacancy {vacancy.pk}: {e}")
            vacancy.extra["renewal_worker_check_done"] = True
            vacancy.save(update_fields=["extra"])
        else:
            # Exactly right — nothing to do
            vacancy.extra["renewal_worker_check_done"] = True
            vacancy.save(update_fields=["extra"])
            logger.info(f"renewal_worker_check: vacancy {vacancy.pk} confirmed exactly {needed} workers")

        handled_vacancies.add(vacancy_id)
    logger.info("task_completed", extra={"task": "renewal_worker_check_task", "processed": None})


@shared_task(name="vacancy.tasks.call.test_heartbeat")
def test_heartbeat():
    logger.warning("✅ test_heartbeat work")
