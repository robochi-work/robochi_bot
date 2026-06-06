import logging
from collections.abc import Iterable
from datetime import date, datetime, timedelta

import sentry_sdk
from celery import shared_task
from django.db import connection
from django.utils import timezone

from telegram.choices import CallStatus, CallType
from telegram.service.group import GroupService
from vacancy.choices import STATUS_APPROVED, STATUS_CLOSED, STATUS_SEARCH_STOPPED
from vacancy.models import Vacancy, VacancyUserCall
from vacancy.services.observers.events import (
    VACANCY_AFTER_START_CALL,
    VACANCY_BEFORE_CALL,
    VACANCY_CLOSE,
    VACANCY_CLOSE_PAYMENT_DOES_NOT_EXIST,
    VACANCY_START_CALL,
)
from vacancy.services.observers.subscriber_setup import telegram_notifier, vacancy_publisher
from vacancy.services.reminder_utils import delete_bot_message, send_and_track

Minutes = int
logger = logging.getLogger(__name__)


def _get_start_aware(vacancy: Vacancy) -> datetime:
    """Get timezone-aware start datetime for vacancy."""
    start_naive = datetime.combine(vacancy.date, vacancy.start_time)
    return timezone.make_aware(start_naive, timezone.get_current_timezone())


def _get_end_aware(vacancy: Vacancy) -> datetime:
    """Get timezone-aware end datetime. Adds +1 day for overnight shifts."""
    end_date = vacancy.date
    if vacancy.end_time < vacancy.start_time:
        end_date = vacancy.date + timedelta(days=1)
    end_naive = datetime.combine(end_date, vacancy.end_time)
    return timezone.make_aware(end_naive, timezone.get_current_timezone())


def _get_owner_contact_phone(vacancy) -> str | None:
    from vacancy.models import VacancyContactPhone

    cp = VacancyContactPhone.objects.filter(vacancy=vacancy, user=vacancy.owner).first()
    return cp.phone if cp else None


def _send_rollcall_reminder(vacancy: Vacancy, call_type: CallType) -> None:
    """Send rollcall reminder to vacancy owner (full text, deletes previous)."""
    from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter
    from vacancy.services.call_markup import get_final_call_markup, get_start_call_markup

    if call_type == CallType.START:
        text = CallVacancyTelegramTextFormatter(vacancy=vacancy).start_call()
        markup = get_start_call_markup(vacancy=vacancy)
        msg_key = "start_call_msg_id"
    else:
        text = CallVacancyTelegramTextFormatter(vacancy=vacancy).final_call()
        markup = get_final_call_markup(vacancy=vacancy)
        msg_key = "final_call_msg_id"

    prev_msg_id = (vacancy.extra or {}).get(msg_key)
    new_msg_id = send_and_track(
        chat_id=vacancy.owner.id, text=text, reply_markup=markup, previous_message_id=prev_msg_id
    )
    if new_msg_id:
        if not vacancy.extra:
            vacancy.extra = {}
        vacancy.extra[msg_key] = new_msg_id


def _escalate_rollcall(vacancy: Vacancy, call_label: str) -> None:
    """Notify admins and kick owner after max reminders exceeded."""
    from service.broadcast_service import TelegramBroadcastService
    from vacancy.services.admin_format import format_group_link, format_user_block_with_contact

    # Delete last reminder message
    for msg_key in ("start_call_msg_id", "final_call_msg_id"):
        prev_msg_id = (vacancy.extra or {}).get(msg_key)
        if prev_msg_id:
            delete_bot_message(vacancy.owner.id, prev_msg_id)
            vacancy.extra.pop(msg_key, None)
    vacancy.save(update_fields=["extra"])

    owner_block = format_user_block_with_contact(vacancy.owner, vacancy)
    group = format_group_link(vacancy)
    admin_text = (
        f"\u26a0\ufe0f \u041d\u0435\u043c\u0430\u0454 \u043f\u0456\u0434\u0442\u0432\u0435\u0440\u0434\u0436\u0435\u043d\u043d\u044f {call_label}\n\n"
        f"\u0412\u0430\u043a\u0430\u043d\u0441\u0456\u044f: {vacancy.address}\n\n"
        f"\u0417\u0430\u043c\u043e\u0432\u043d\u0438\u043a:\n{owner_block}"
        f"{group}"
    )
    try:
        broadcast = TelegramBroadcastService(notifier=telegram_notifier)
        broadcast.admin_broadcast(text=admin_text, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"_escalate_rollcall ({call_label}): admin broadcast failed: {e}")
    owner = vacancy.owner
    if vacancy.group:
        try:
            GroupService.kick_user(chat_id=vacancy.group.id, user_id=owner.id)
        except Exception as e:
            logger.warning(f"_escalate_rollcall ({call_label}): kick owner failed: {e}")
        msg_id = vacancy.extra.get("employer_invite_msg_id")
        if msg_id:
            try:
                from telegram.handlers.bot_instance import bot

                bot.delete_message(chat_id=owner.id, message_id=msg_id)
            except Exception as e:
                logger.warning(f"_escalate_rollcall: delete invite msg failed: {e}")
    # Auto-confirm rollcall
    members = vacancy.members
    members_count = members.count()
    if members_count == 0:
        vacancy_publisher.notify(VACANCY_CLOSE, data={"vacancy": vacancy})
        from telegram.handlers.bot_instance import bot as _bot

        try:
            _bot.send_message(chat_id=owner.id, text=f"Вакансію за адресою {vacancy.address} закрито.")
        except Exception:
            pass
    else:
        from vacancy.models import VacancyUserCall
        from vacancy.services.call import create_vacancy_call

        if not vacancy.first_rollcall_passed:
            ct = CallType.START
            create_vacancy_call(vacancy=vacancy, call_type=ct, status=CallStatus.CREATED)
            VacancyUserCall.objects.filter(vacancy_user__in=members, call_type=ct).update(status=CallStatus.CONFIRM)
            # Save confirmed workers to extra for invoice calculation
            extra_calls = vacancy.extra.get("calls", {})
            extra_calls[ct] = list(members.values_list("user_id", flat=True))
            vacancy.extra["calls"] = extra_calls
            vacancy.first_rollcall_passed = True
            vacancy.save(update_fields=["first_rollcall_passed", "extra"])
        elif not vacancy.second_rollcall_passed:
            ct = CallType.AFTER_START
            create_vacancy_call(vacancy=vacancy, call_type=ct, status=CallStatus.CREATED)
            VacancyUserCall.objects.filter(vacancy_user__in=members, call_type=ct).update(status=CallStatus.CONFIRM)
            # Save confirmed workers to extra for invoice calculation
            extra_calls = vacancy.extra.get("calls", {})
            extra_calls[ct] = list(members.values_list("user_id", flat=True))
            vacancy.extra["calls"] = extra_calls
            vacancy.second_rollcall_passed = True
            vacancy.save(update_fields=["second_rollcall_passed", "extra"])
        from telegram.handlers.bot_instance import bot as _bot

        try:
            _auto_text = f"Перекличку підтверджено автоматично. Працівників: {members_count}."
            _bot.send_message(chat_id=owner.id, text=_auto_text)
        except Exception:
            pass

        # After auto-confirm of 2nd rollcall: issue invoice and block employer
        if vacancy.second_rollcall_passed and vacancy.first_rollcall_passed:
            from vacancy.choices import STATUS_AWAITING_PAYMENT
            from vacancy.services.invoice import send_vacancy_invoice

            vacancy.status = STATUS_AWAITING_PAYMENT
            vacancy.search_active = False
            vacancy.save(update_fields=["status", "search_active"])
            try:
                send_vacancy_invoice(notifier=telegram_notifier, vacancy=vacancy)
            except Exception:
                import sentry_sdk

                sentry_sdk.capture_exception()
            logger.info("escalate_rollcall_invoice", extra={"vacancy_id": vacancy.pk, "workers": members_count})


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
            ChannelMessage.objects.filter(channel_id=vacancy.channel.id, extra__vacancy_id=vacancy.id)
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
    """Vacancies inside the 2h-before-start window for BEFORE_START rollcall.

    Two defense layers against re-sending the notice after continue_search:
    (1) extra["pre_call_done"] flag — set after first successful dispatch,
        cleared only when a NEW cycle begins (resume_search/renewal/moderation).
    (2) extra["original_start_datetime"] anchor — used instead of the live
        start_time, which continue_search may shift forward.
    """
    vacancies = Vacancy.objects.filter(status=STATUS_APPROVED, date=date.today())

    naive_now = datetime.now()
    aware_now = timezone.make_aware(naive_now, timezone.get_current_timezone())
    filtered_vacancies = []
    for vacancy in vacancies:
        # Layer 1: skip if 2h notice already dispatched in current cycle.
        if (vacancy.extra or {}).get("pre_call_done"):
            continue

        # Layer 2: anchor window to the original cycle start, not live start_time.
        orig_iso = (vacancy.extra or {}).get("original_start_datetime")
        if orig_iso:
            try:
                start_aware = datetime.fromisoformat(orig_iso)
                if timezone.is_naive(start_aware):
                    start_aware = timezone.make_aware(start_aware, timezone.get_current_timezone())
            except (ValueError, TypeError):
                start_aware = _get_start_aware(vacancy)
        else:
            # Legacy fallback for vacancies created before this field existed.
            start_aware = _get_start_aware(vacancy)

        before_start_time = start_aware - timedelta(minutes=delay)
        if before_start_time < aware_now < start_aware:
            filtered_vacancies.append(vacancy)
    return filtered_vacancies


def get_start_vacancies(delay: Minutes = 10) -> Iterable[Vacancy]:
    vacancies = Vacancy.objects.filter(status=STATUS_APPROVED, date=date.today())

    naive_now = datetime.now()
    aware_now = timezone.make_aware(naive_now, timezone.get_current_timezone())
    filtered_vacancies = []
    for vacancy in vacancies:
        start_aware = _get_start_aware(vacancy)

        after_start_time = start_aware + timedelta(minutes=delay)
        if after_start_time > aware_now > start_aware:
            filtered_vacancies.append(vacancy)
    return filtered_vacancies


def get_final_vacancies() -> Iterable[Vacancy]:
    vacancies = Vacancy.objects.filter(status=STATUS_APPROVED, date=date.today())

    naive_now = datetime.now()
    aware_now = timezone.make_aware(naive_now, timezone.get_current_timezone())
    filtered_vacancies = []
    for vacancy in vacancies:
        end_aware = _get_end_aware(vacancy)

        if aware_now > end_aware:
            filtered_vacancies.append(vacancy)
    return filtered_vacancies


def get_final_call_vacancies(before_end: Minutes = 60) -> Iterable[Vacancy]:
    """Vacancies where end_time is within `before_end` minutes from now (for final rollcall)."""
    vacancies = Vacancy.objects.filter(status=STATUS_APPROVED, date=date.today())

    naive_now = datetime.now()
    aware_now = timezone.make_aware(naive_now, timezone.get_current_timezone())
    filtered_vacancies = []
    for vacancy in vacancies:
        end_aware = _get_end_aware(vacancy)
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
                            chat_id=call.vacancy_user.vacancy.group.id, user_id=call.vacancy_user.user.id
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
        date=date.today(), status__in=[STATUS_APPROVED, STATUS_SEARCH_STOPPED], first_rollcall_passed=False
    ):
        start_aware = _get_start_aware(v)
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
    for v in Vacancy.objects.filter(date=date.today(), status=STATUS_SEARCH_STOPPED, second_rollcall_passed=False):
        end_aware = _get_end_aware(v)
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
            end_time = _get_end_aware(vacancy)
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
    for vacancy in Vacancy.objects.filter(closed_at__isnull=False, closed_at__lte=threshold, group__isnull=False):
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
        # Skip if workers exist and lifecycle not finished (rollcalls/payment pending)
        has_members = vacancy.members.exists()
        if has_members and not vacancy.extra.get("payment_checked", False):
            logger.info(f"close_lifecycle_timer_task: skipping vacancy {vacancy.pk} (has members, lifecycle active)")
            continue
        logger.info(f"close_lifecycle_timer_task: closing vacancy {vacancy.pk} (search_stopped_at timer)")
        vacancy_publisher.notify(VACANCY_CLOSE, data={"vacancy": vacancy})
        processed += 1
    # Case c: paid vacancies — 3h after payment, free group
    from payment.models import MonobankPayment

    paid_vacancies = Vacancy.objects.filter(status="paid", group__isnull=False)
    for vacancy in paid_vacancies:
        # Admin-marked paid: use search_stopped_at or closed_at as reference
        if vacancy.extra.get("admin_marked_paid"):
            ref_time = vacancy.search_stopped_at or vacancy.closed_at
            if ref_time and ref_time <= threshold:
                logger.info(f"close_lifecycle_timer_task: closing vacancy {vacancy.pk} (admin paid, 3h passed)")
                vacancy_publisher.notify(VACANCY_CLOSE, data={"vacancy": vacancy})
                processed += 1
            continue
        # Monobank paid: 3h after last successful payment
        last_payment = (
            MonobankPayment.objects.filter(vacancy=vacancy, status=MonobankPayment.Status.SUCCESS)
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
    from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

    KICK_AFTER = 300  # 5 minutes in seconds
    REMIND_MINUTES = {1, 2, 3, 4}

    pending = VacancyUserCall.objects.filter(
        call_type=CallType.WORKER_JOIN_CONFIRM.value, status=CallStatus.SENT.value
    ).select_related("vacancy_user__user", "vacancy_user__vacancy__group")

    for call in pending:
        elapsed = (timezone.now() - call.created_at).total_seconds()
        user = call.vacancy_user.user
        vacancy = call.vacancy_user.vacancy

        if elapsed >= KICK_AFTER:
            # Worker is NOT in group yet — mark as LEFT, notify
            from telegram.models import Status
            from vacancy.models import VacancyUser

            VacancyUser.objects.filter(user=user, vacancy=vacancy, status=Status.PENDING_CONFIRM).update(
                status=Status.LEFT
            )
            call.status = CallStatus.REJECT.value
            call.save(update_fields=["status"])
            # Clean up contact phone so re-apply starts fresh
            from vacancy.models import VacancyContactPhone

            VacancyContactPhone.objects.filter(vacancy=vacancy, user=user).delete()
            # Delete confirm message with buttons
            try:
                confirm_msgs = vacancy.extra.get("confirm_msg_ids", {}) if vacancy.extra else {}
                msg_id = confirm_msgs.get(str(user.id))
                if msg_id:
                    bot.delete_message(chat_id=user.id, message_id=msg_id)
                    del confirm_msgs[str(user.id)]
                    vacancy.extra["confirm_msg_ids"] = confirm_msgs
                    vacancy.save(update_fields=["extra"])
            except Exception:
                pass
            try:
                bot.send_message(
                    chat_id=user.id,
                    text="Ви не підтвердили участь у вакансії протягом 5 хвилин. Вашу заявку скасовано.",
                )
            except Exception:
                pass
            # Send cabinet link
            try:
                from django.conf import settings
                from django.urls import reverse
                from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

                check_url = reverse("telegram:check_web_app")
                url = settings.BASE_URL.rstrip("/") + check_url + "?next=/"
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton(text="Перейти", web_app=WebAppInfo(url=url)))
                bot.send_message(
                    chat_id=user.id,
                    text="Перейдіть у Власний кабінет— тут ви зможете обрати роботу, знайти групу Вашої вакансії та отримати підказки користування сервісом.",
                    reply_markup=markup,
                )
            except Exception:
                pass
            logger.info(f"worker_join_confirm: removed user {user.id} (no confirm in 5 min)")
            continue

        # Reminder at minutes 1, 2, 3, 4 — only in first 30s of that minute
        elapsed_minute = int(elapsed // 60)
        in_reminder_window = (elapsed % 60) < 30
        if elapsed_minute in REMIND_MINUTES and in_reminder_window:
            from vacancy.services.call_markup import get_worker_join_confirm_markup

            prev_msg_id = (vacancy.extra or {}).get("confirm_msg_ids", {}).get(str(user.id))
            new_msg_id = send_and_track(
                chat_id=user.id,
                text=CallVacancyTelegramTextFormatter(vacancy).worker_join_confirm(),
                reply_markup=get_worker_join_confirm_markup(vacancy),
                previous_message_id=prev_msg_id,
            )
            if new_msg_id:
                if not vacancy.extra:
                    vacancy.extra = {}
                confirm_msgs = vacancy.extra.get("confirm_msg_ids", {})
                confirm_msgs[str(user.id)] = new_msg_id
                vacancy.extra["confirm_msg_ids"] = confirm_msgs
                vacancy.save(update_fields=["extra"])
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

    from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter
    from vacancy.services.call_markup import get_renewal_offer_markup

    candidates = (
        Vacancy.objects.filter(second_rollcall_passed=True, closed_at__isnull=True)
        .filter(extra__is_paid=True)
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
            new_msg_id = send_and_track(
                chat_id=vacancy.owner.id,
                text=CallVacancyTelegramTextFormatter(vacancy).renewal_offer(),
                reply_markup=get_renewal_offer_markup(vacancy),
            )
            if not new_msg_id:
                logger.warning(f"renewal_offer_task: initial send failed for vacancy {vacancy.pk}")
                continue
            extra["renewal_started"] = True
            extra["renewal_sent_at"] = timezone.now().timestamp()
            extra["renewal_reminders"] = 0
            extra["renewal_msg_id"] = new_msg_id
            vacancy.save(update_fields=["extra"])

        elif not extra.get("renewal_expired"):
            elapsed = timezone.now().timestamp() - extra.get("renewal_sent_at", 0)
            if elapsed < _RENEWAL_OFFER_INTERVAL:
                continue

            reminders = extra.get("renewal_reminders", 0)
            if reminders >= _RENEWAL_MAX_REMINDERS:
                # Delete last reminder on expiry
                delete_bot_message(vacancy.owner.id, extra.get("renewal_msg_id"))
                extra["renewal_expired"] = True
                extra["renewal_offered"] = True
                extra.pop("renewal_msg_id", None)
                vacancy.save(update_fields=["extra"])
                logger.info(f"renewal_offer_task: offer expired for vacancy {vacancy.pk}")
            else:
                prev_msg_id = extra.get("renewal_msg_id")
                new_msg_id = send_and_track(
                    chat_id=vacancy.owner.id,
                    text=CallVacancyTelegramTextFormatter(vacancy).renewal_offer(),
                    reply_markup=get_renewal_offer_markup(vacancy),
                    previous_message_id=prev_msg_id,
                )
                if not new_msg_id:
                    logger.warning(f"renewal_offer_task: reminder failed for vacancy {vacancy.pk}")
                    continue
                extra["renewal_reminders"] = reminders + 1
                extra["renewal_sent_at"] = timezone.now().timestamp()
                extra["renewal_msg_id"] = new_msg_id
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
        call_type=CallType.RENEWAL_WORKER.value, status=CallStatus.SENT.value
    ).select_related("vacancy_user__user", "vacancy_user__vacancy__group", "vacancy_user__vacancy__owner")

    # Group by vacancy to detect "all answered" after kicks
    vacancy_ids_with_pending = set()

    for call in pending:
        elapsed = (timezone.now() - call.created_at).total_seconds()
        user = call.vacancy_user.user
        vacancy = call.vacancy_user.vacancy
        vacancy_ids_with_pending.add(vacancy.pk)

        if elapsed >= _RENEWAL_WORKER_INTERVAL * _RENEWAL_WORKER_MAX_REMINDERS:
            # Delete last reminder before kicking
            renewal_msgs = (vacancy.extra or {}).get("renewal_worker_msg_ids", {})
            prev_msg_id = renewal_msgs.get(str(user.id))
            delete_bot_message(user.id, prev_msg_id)
            # Send final message (stays permanently)
            try:
                bot.send_message(chat_id=user.id, text="Час вичерпано. Вас видалено з групи вакансії.")
            except Exception:
                pass
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
            from vacancy.services.call_markup import get_renewal_worker_markup

            renewal_msgs = (vacancy.extra or {}).get("renewal_worker_msg_ids", {})
            prev_msg_id = renewal_msgs.get(str(user.id))
            new_msg_id = send_and_track(
                chat_id=user.id,
                text=CallVacancyTelegramTextFormatter(vacancy).renewal_worker_ask(),
                reply_markup=get_renewal_worker_markup(vacancy),
                previous_message_id=prev_msg_id,
            )
            if new_msg_id:
                if not vacancy.extra:
                    vacancy.extra = {}
                renewal_msgs = vacancy.extra.get("renewal_worker_msg_ids", {})
                renewal_msgs[str(user.id)] = new_msg_id
                vacancy.extra["renewal_worker_msg_ids"] = renewal_msgs
                vacancy.save(update_fields=["extra"])

    # Check vacancies where poll may have just completed (all responded)
    handled_vacancies = set()
    answered_vacancies = (
        VacancyUserCall.objects.filter(call_type=CallType.RENEWAL_WORKER.value)
        .exclude(status=CallStatus.SENT.value)
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
            call_type=CallType.RENEWAL_WORKER.value, status=CallStatus.SENT.value, vacancy_user__vacancy_id=vacancy_id
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


@shared_task
def disputed_rollcall_reminders_task():
    """Stage 3.C: send up to 12 reminders (every 5 min) to employers stuck in
    a partially-unchecked 2nd rollcall (Scenario Б).

    Triggered every 30 seconds. Only acts when 5 minutes have passed since
    the previous reminder, and stops after 12 reminders (then admin is
    the only path forward).
    """
    from vacancy.services.call_markup import get_rollcall_reminder_markup
    from vacancy.services.disputed_rollcall import DISPUTED_KEY, increment_reminders

    logger.info("task_started", extra={"task": "disputed_rollcall_reminders_task"})
    connection.close()

    REMINDER_INTERVAL_MIN = 5
    MAX_REMINDERS = 12
    now = timezone.now()
    processed = 0

    candidates = Vacancy.objects.filter(extra__has_key=DISPUTED_KEY)
    for vacancy in candidates:
        state = (vacancy.extra or {}).get(DISPUTED_KEY) or {}
        # Skip Scenario В (full uncheck) — employer is blocked, no reminders
        if state.get("is_full_uncheck"):
            continue
        if int(state.get("reminders_count", 0)) >= MAX_REMINDERS:
            continue

        last_iso = state.get("last_reminder_at")
        if last_iso:
            try:
                last_dt = datetime.fromisoformat(last_iso)
                if (now - last_dt) < timedelta(minutes=REMINDER_INTERVAL_MIN):
                    continue
            except (TypeError, ValueError):
                pass

        try:
            from telegram.handlers.bot_instance import bot as _bot

            _bot.send_message(
                chat_id=vacancy.owner.id,
                text="Підтвердіть наявність робочих у другій перекличці.",
                reply_markup=get_rollcall_reminder_markup(vacancy, CallType.AFTER_START),
            )
            increment_reminders(vacancy)
            processed += 1
        except Exception:
            sentry_sdk.capture_exception()

    logger.info(
        "task_completed",
        extra={"task": "disputed_rollcall_reminders_task", "processed": processed},
    )
