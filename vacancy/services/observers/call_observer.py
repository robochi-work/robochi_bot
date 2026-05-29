import logging
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import sentry_sdk
from django.utils import timezone

from service.broadcast_service import TelegramBroadcastService
from service.notifications_impl import TelegramNotifier
from telegram.choices import CallStatus, CallType
from telegram.handlers.bot_instance import get_bot
from telegram.service.group import GroupService
from user.choices import BlockReason, BlockType
from user.services import BlockService
from vacancy.models import Vacancy, VacancyUserCall
from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter
from vacancy.services.call_markup import (
    get_before_start_call_markup,
    get_final_call_markup,
    get_start_call_markup,
)
from vacancy.services.invoice import send_vacancy_invoice
from vacancy.services.observers.publisher import Observer
from vacancy.services.reminder_utils import delete_bot_message, send_and_track

logger = logging.getLogger(__name__)


class VacancyBeforeCallObserver(Observer):
    def __init__(self, notifier: TelegramNotifier | None = None):
        self.notifier = notifier

    def check_before_start(self, vacancy: Vacancy):
        from datetime import datetime

        start_naive = datetime.combine(vacancy.date, vacancy.start_time)
        start_aware = timezone.make_aware(start_naive, timezone.get_current_timezone())
        two_hours_before = start_aware - timedelta(hours=2)

        for member in vacancy.members:
            user_answer_exists = VacancyUserCall.objects.filter(
                vacancy_user=member,
                call_type=CallType.BEFORE_START,
            ).exists()
            if not user_answer_exists:
                # Skip workers already confirmed at start rollcall
                already_confirmed = VacancyUserCall.objects.filter(
                    vacancy_user=member,
                    call_type=CallType.START,
                    status=CallStatus.CONFIRM,
                ).exists()
                if already_confirmed:
                    continue
                # Skip workers who joined after the 2h-before mark —
                # they already confirmed via join_confirm
                join_confirmed = VacancyUserCall.objects.filter(
                    vacancy_user=member,
                    call_type=CallType.WORKER_JOIN_CONFIRM,
                    status=CallStatus.CONFIRM,
                    created_at__gte=two_hours_before,
                ).exists()
                if join_confirmed:
                    logger.info(
                        "before_start_skipped",
                        extra={"user_id": member.user.id, "vacancy_id": vacancy.id, "reason": "joined_after_2h_mark"},
                    )
                    continue
                VacancyUserCall.objects.update_or_create(
                    vacancy_user=member,
                    call_type=CallType.BEFORE_START,
                    defaults={
                        "status": CallStatus.SENT,
                    },
                )
                text = CallVacancyTelegramTextFormatter(vacancy=vacancy).before_start_call()
                new_msg_id = send_and_track(
                    chat_id=member.user.id,
                    text=text,
                    reply_markup=get_before_start_call_markup(vacancy=vacancy),
                )
                if new_msg_id:
                    if not vacancy.extra:
                        vacancy.extra = {}
                    bs_msgs = vacancy.extra.get("before_start_msg_ids", {})
                    bs_msgs[str(member.user.id)] = new_msg_id
                    vacancy.extra["before_start_msg_ids"] = bs_msgs
                    vacancy.save(update_fields=["extra"])

    @staticmethod
    def check_before_5_start(vacancy: Vacancy):
        KICK_AFTER = 300  # 5 minutes in seconds
        REMIND_MINUTES = {1, 2, 3, 4}

        for member in vacancy.members:
            try:
                user_answer = VacancyUserCall.objects.filter(
                    vacancy_user=member,
                    call_type=CallType.BEFORE_START,
                ).first()
                if not user_answer or user_answer.status == CallStatus.CONFIRM:
                    continue

                elapsed = (timezone.now() - user_answer.created_at).total_seconds()

                if elapsed >= KICK_AFTER:
                    if BlockService.is_blocked(member.user):
                        continue
                    # Delete last reminder before kicking
                    prev_msg_id = (vacancy.extra or {}).get("before_start_msg_ids", {}).get(str(member.user.id))
                    delete_bot_message(member.user.id, prev_msg_id)
                    GroupService.kick_user(chat_id=member.vacancy.group.id, user_id=member.user.id)
                    BlockService.auto_block_rollcall_reject(user=member.user)
                    try:
                        get_bot().send_message(
                            member.user.id,
                            CallVacancyTelegramTextFormatter.auto_block_message(reason="ігнорування переклички"),
                        )
                    except Exception:
                        sentry_sdk.capture_exception()
                    continue

                # Reminder at minutes 1, 2, 3, 4
                elapsed_minute = int(elapsed // 60)
                in_reminder_window = (elapsed % 60) < 30
                if elapsed_minute in REMIND_MINUTES and in_reminder_window:
                    from vacancy.services.call_markup import get_before_start_call_markup

                    prev_msg_id = (vacancy.extra or {}).get("before_start_msg_ids", {}).get(str(member.user.id))
                    new_msg_id = send_and_track(
                        chat_id=member.user.id,
                        text=CallVacancyTelegramTextFormatter(vacancy=vacancy).before_start_call(),
                        reply_markup=get_before_start_call_markup(vacancy=vacancy),
                        previous_message_id=prev_msg_id,
                    )
                    if new_msg_id:
                        if not vacancy.extra:
                            vacancy.extra = {}
                        bs_msgs = vacancy.extra.get("before_start_msg_ids", {})
                        bs_msgs[str(member.user.id)] = new_msg_id
                        vacancy.extra["before_start_msg_ids"] = bs_msgs
                        vacancy.save(update_fields=["extra"])
            except Exception:
                sentry_sdk.capture_exception()

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy: Vacancy = data["vacancy"]
        self.check_before_start(vacancy=vacancy)
        self.check_before_5_start(vacancy=vacancy)


class VacancyStartCallObserver(Observer):
    def __init__(self, notifier: TelegramNotifier | None = None):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data["vacancy"]
        workers = vacancy.members.count()
        logger.info("rollcall_started", extra={"vacancy_id": vacancy.id, "call_type": "start", "workers": workers})
        text = CallVacancyTelegramTextFormatter(vacancy=vacancy).start_call()
        new_msg_id = send_and_track(
            chat_id=vacancy.owner.id,
            text=text,
            reply_markup=get_start_call_markup(vacancy=vacancy),
        )
        if new_msg_id:
            if not vacancy.extra:
                vacancy.extra = {}
            vacancy.extra["start_call_msg_id"] = new_msg_id
            vacancy.save(update_fields=["extra"])


class VacancyStartCallFailObserver(Observer):
    def __init__(self, notifier: TelegramNotifier | None = None):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy: Vacancy = data["vacancy"]

        from vacancy.services.call_markup import get_admin_check_rollcall_markup

        broadcast_service = TelegramBroadcastService(notifier=self.notifier)
        broadcast_service.admin_broadcast(
            text=CallVacancyTelegramTextFormatter(vacancy=vacancy).admin_start_call_fail_detailed(),
            parse_mode="HTML",
            reply_markup=get_admin_check_rollcall_markup(vacancy, CallType.START),
        )

        users_call_reject = VacancyUserCall.objects.filter(
            vacancy_user__in=vacancy.members,
            status=CallStatus.REJECT,
            call_type=CallType.START,
        )
        declined_ids = list(users_call_reject.values_list("vacancy_user__user_id", flat=True))
        logger.info("rollcall_result", extra={"vacancy_id": vacancy.id, "confirmed": [], "declined": declined_ids})
        text = CallVacancyTelegramTextFormatter(vacancy=vacancy).start_call_fail()
        for call in users_call_reject:
            user = call.vacancy_user.user
            self.notifier.notify(
                recipient=SimpleNamespace(chat_id=user.id),
                text=text,
            )
            # Кик из группы вакансии
            if vacancy.group:
                try:
                    GroupService.kick_user(chat_id=vacancy.group.id, user_id=user.id)
                except Exception:
                    sentry_sdk.capture_exception()
            # Временная блокировка — причина employer_uncheck
            if BlockService.is_blocked(user):
                continue
            BlockService.block_user(
                user=user,
                block_type=BlockType.TEMPORARY,
                reason=BlockReason.EMPLOYER_UNCHECK,
                blocked_by=vacancy.owner,
            )
            try:
                get_bot().send_message(
                    user.id,
                    CallVacancyTelegramTextFormatter.auto_block_message(reason="відсутність на перекличці"),
                )
            except Exception:
                sentry_sdk.capture_exception()


class VacancyAfterStartCallObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy: Vacancy = data["vacancy"]
        workers = vacancy.members.count()
        logger.info(
            "rollcall_started", extra={"vacancy_id": vacancy.id, "call_type": "after_start", "workers": workers}
        )
        text = CallVacancyTelegramTextFormatter(vacancy=vacancy).final_call()
        new_msg_id = send_and_track(
            chat_id=vacancy.owner.id,
            text=text,
            reply_markup=get_final_call_markup(vacancy=vacancy),
        )
        if new_msg_id:
            if not vacancy.extra:
                vacancy.extra = {}
            vacancy.extra["final_call_msg_id"] = new_msg_id
            vacancy.save(update_fields=["extra"])


class VacancyAfterStartCallSuccessObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy: Vacancy = data["vacancy"]
        send_vacancy_invoice(notifier=self.notifier, vacancy=vacancy)


class VacancyAfterStartCallFailObserver(Observer):
    def __init__(self, notifier: TelegramNotifier | None = None):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data["vacancy"]

        from vacancy.services.call_markup import get_admin_check_rollcall_markup

        broadcast_service = TelegramBroadcastService(notifier=self.notifier)
        broadcast_service.admin_broadcast(
            text=CallVacancyTelegramTextFormatter(vacancy=vacancy).admin_after_start_call_fail_detailed(),
            parse_mode="HTML",
            reply_markup=get_admin_check_rollcall_markup(vacancy),
        )

        users_call_reject = VacancyUserCall.objects.filter(
            vacancy_user__in=vacancy.members,
            status=CallStatus.REJECT,
            call_type=CallType.AFTER_START,
        )
        text = CallVacancyTelegramTextFormatter(vacancy=vacancy).start_call_fail()
        for call in users_call_reject:
            user = call.vacancy_user.user
            self.notifier.notify(
                recipient=SimpleNamespace(chat_id=user.id),
                text=text,
            )
            # Кик из группы вакансии
            if vacancy.group:
                try:
                    GroupService.kick_user(chat_id=vacancy.group.id, user_id=user.id)
                except Exception:
                    sentry_sdk.capture_exception()
            # Временная блокировка — причина employer_uncheck
            if BlockService.is_blocked(user):
                continue
            BlockService.block_user(
                user=user,
                block_type=BlockType.TEMPORARY,
                reason=BlockReason.EMPLOYER_UNCHECK,
                blocked_by=vacancy.owner,
            )
            try:
                get_bot().send_message(
                    user.id,
                    CallVacancyTelegramTextFormatter.auto_block_message(reason="відсутність на перекличці"),
                )
            except Exception:
                sentry_sdk.capture_exception()
