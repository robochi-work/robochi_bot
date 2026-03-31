from types import SimpleNamespace
from typing import Any
from service.notifications import NotificationMethod
from service.notifications_impl import TelegramNotifier
from .publisher import Observer
from ..call_formatter import CallVacancyTelegramTextFormatter
from ..call_markup import get_vacancy_my_list_markup


class VacancyApprovedUserObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data['vacancy']

        self.notifier.notify(
            recipient=SimpleNamespace(chat_id=vacancy.owner.id,),
            method=NotificationMethod.TEXT,
            text=CallVacancyTelegramTextFormatter.vacancy_approved_user(),
            reply_markup=get_vacancy_my_list_markup(),
        )
