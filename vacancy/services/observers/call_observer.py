from types import SimpleNamespace
from typing import Any, Optional

from django.conf import settings
from telebot.types import InlineKeyboardMarkup, LabeledPrice
from django.utils import timezone
from datetime import timedelta

from service.broadcast_service import TelegramBroadcastService
from service.notifications import NotificationMethod
from service.notifications_impl import TelegramNotifier
from telegram.choices import Status, CallType, CallStatus
from telegram.service.group import GroupService
from vacancy.models import Vacancy, VacancyUserCall
from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter
from vacancy.services.call_markup import get_before_start_call_markup, get_start_call_markup, get_final_call_markup, \
    get_final_call_success_markup
from vacancy.services.invoice import get_vacancy_invoice_amount, get_vacancy_invoice_data, send_vacancy_invoice
from vacancy.services.observers.publisher import Observer
from vacancy.services.vacancy_formatter import VacancyTelegramTextFormatter


class VacancyBeforeCallObserver(Observer):
    def __init__(self, notifier: Optional[TelegramNotifier] = None):
        self.notifier = notifier

    def check_before_start(self, vacancy: Vacancy):

        for member in vacancy.members:
            user_answer_exists = VacancyUserCall.objects.filter(
                vacancy_user=member,
                call_type=CallType.BEFORE_START,
            ).exists()
            if not user_answer_exists:
                VacancyUserCall.objects.update_or_create(
                    vacancy_user=member,
                    defaults={
                        'call_type': CallType.BEFORE_START,
                        'status': CallStatus.SENT,
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
            except Exception as e:
                ...

            if kick:
                GroupService.kick_user(chat_id=member.vacancy.group.id, user_id=member.user.id)

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy: Vacancy = data['vacancy']
        self.check_before_start(vacancy=vacancy)
        self.check_before_20_start(vacancy=vacancy)


class VacancyStartCallObserver(Observer):
    def __init__(self, notifier: Optional[TelegramNotifier] = None):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data['vacancy']
        text = CallVacancyTelegramTextFormatter(vacancy=vacancy).start_call()
        self.notifier.notify(
            recipient=SimpleNamespace(chat_id=vacancy.owner.id),
            text=text,
            method=NotificationMethod.TEXT,
            reply_markup=get_start_call_markup(vacancy=vacancy),
        )

class VacancyStartCallFailObserver(Observer):
    def __init__(self, notifier: Optional[TelegramNotifier] = None):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy: Vacancy = data['vacancy']

        broadcast_service = TelegramBroadcastService(notifier=self.notifier)
        broadcast_service.admin_broadcast(
            text=CallVacancyTelegramTextFormatter(vacancy=vacancy).admin_start_call_fail(),
        )

        users_call_reject = VacancyUserCall.objects.filter(
            vacancy_user__in=vacancy.members,
            status=CallStatus.REJECT,
            call_type=CallType.START,
        )
        text = CallVacancyTelegramTextFormatter(vacancy=vacancy).start_call_fail()
        for call in users_call_reject:
            self.notifier.notify(
                recipient=SimpleNamespace(chat_id=call.vacancy_user.user.id),
                text=text,
            )



class VacancyAfterStartCallObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy: Vacancy = data['vacancy']
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
        vacancy: Vacancy = data['vacancy']
        send_vacancy_invoice(notifier=self.notifier, vacancy=vacancy)

class VacancyAfterStartCallFailObserver(Observer):
    def __init__(self, notifier: Optional[TelegramNotifier] = None):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data['vacancy']

        broadcast_service = TelegramBroadcastService(notifier=self.notifier)
        broadcast_service.admin_broadcast(
            text=CallVacancyTelegramTextFormatter(vacancy=vacancy).admin_after_start_call_fail(),
        )

        users_call_reject = VacancyUserCall.objects.filter(
            vacancy_user__in=vacancy.members,
            status=CallStatus.REJECT,
            call_type=CallType.START,
        )
        text = CallVacancyTelegramTextFormatter(vacancy=vacancy).start_call_fail()
        for call in users_call_reject:
            self.notifier.notify(
                recipient=SimpleNamespace(chat_id=call.vacancy_user.user.id),
                text=text,
            )

