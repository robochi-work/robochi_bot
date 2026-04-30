import logging
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import sentry_sdk
from django.utils import timezone

from service.broadcast_service import TelegramBroadcastService
from service.notifications import NotificationMethod
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

logger = logging.getLogger(__name__)


class VacancyBeforeCallObserver(Observer):
    def __init__(self, notifier: TelegramNotifier | None = None):
        self.notifier = notifier

    def check_before_start(self, vacancy: Vacancy):
        for member in vacancy.members:
            user_answer_exists = VacancyUserCall.objects.filter(
                vacancy_user=member,
                call_type=CallType.BEFORE_START,
            ).exists()
            if not user_answer_exists:
                # Skip if worker joined less than 2h before start (already confirmed recently)
                join_confirm = VacancyUserCall.objects.filter(
                    vacancy_user=member,
                    call_type=CallType.WORKER_JOIN_CONFIRM.value,
                    status=CallStatus.CONFIRM.value,
                ).first()
                if join_confirm:
                    start_naive = datetime.combine(vacancy.date, vacancy.start_time)
                    start_aware = timezone.make_aware(start_naive, timezone.get_current_timezone())
                    joined_less_than_2h = (start_aware - join_confirm.created_at).total_seconds() < 7200
                    if joined_less_than_2h:
                        continue
                VacancyUserCall.objects.update_or_create(
                    vacancy_user=member,
                    call_type=CallType.BEFORE_START,
                    defaults={
                        "status": CallStatus.SENT,
                    },
                )
                text = CallVacancyTelegramTextFormatter(vacancy=vacancy).before_start_call()
                self.notifier.notify(
                    recipient=SimpleNamespace(chat_id=member.user.id),
                    text=text,
                    method=NotificationMethod.TEXT,
                    reply_markup=get_before_start_call_markup(vacancy=vacancy),
                )

    @staticmethod
    def check_before_20_start(vacancy: Vacancy):
        for member in vacancy.members:
            kick = False

            try:
                twenty_minutes_ago = timezone.now() - timedelta(minutes=20)
                user_answer = VacancyUserCall.objects.filter(
                    vacancy_user=member,
                    call_type=CallType.BEFORE_START,
                    created_at__lte=twenty_minutes_ago,
                ).first()
                if user_answer and not user_answer.status == CallStatus.CONFIRM:
                    kick = True
            except Exception:
                sentry_sdk.capture_exception()

            if kick:
                GroupService.kick_user(chat_id=member.vacancy.group.id, user_id=member.user.id)
                BlockService.auto_block_rollcall_reject(user=member.user)
                try:
                    get_bot().send_message(
                        member.user.id,
                        CallVacancyTelegramTextFormatter.auto_block_message(reason="ігнорування переклички"),
                    )
                except Exception:
                    sentry_sdk.capture_exception()

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy: Vacancy = data["vacancy"]
        self.check_before_start(vacancy=vacancy)
        self.check_before_20_start(vacancy=vacancy)


class VacancyStartCallObserver(Observer):
    def __init__(self, notifier: TelegramNotifier | None = None):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data["vacancy"]
        workers = vacancy.members.count()
        logger.info("rollcall_started", extra={"vacancy_id": vacancy.id, "call_type": "start", "workers": workers})
        text = CallVacancyTelegramTextFormatter(vacancy=vacancy).start_call()
        self.notifier.notify(
            recipient=SimpleNamespace(chat_id=vacancy.owner.id),
            text=text,
            method=NotificationMethod.TEXT,
            reply_markup=get_start_call_markup(vacancy=vacancy),
        )


class VacancyStartCallFailObserver(Observer):
    def __init__(self, notifier: TelegramNotifier | None = None):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy: Vacancy = data["vacancy"]

        broadcast_service = TelegramBroadcastService(notifier=self.notifier)
        broadcast_service.admin_broadcast(
            text=CallVacancyTelegramTextFormatter(vacancy=vacancy).admin_start_call_fail(),
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
        self.notifier.notify(
            recipient=SimpleNamespace(chat_id=vacancy.owner.id),
            text=text,
            method=NotificationMethod.TEXT,
            reply_markup=get_final_call_markup(vacancy=vacancy),
        )


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

        broadcast_service = TelegramBroadcastService(notifier=self.notifier)
        broadcast_service.admin_broadcast(
            text=CallVacancyTelegramTextFormatter(vacancy=vacancy).admin_after_start_call_fail(),
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
