from types import SimpleNamespace
from typing import Any
from django.utils.translation import gettext as _
from service.notifications import NotificationMethod
from service.notifications_impl import TelegramNotifier
from .publisher import Observer


class VacancyApprovedUserObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data['vacancy']

        self.notifier.notify(
            recipient=SimpleNamespace(chat_id=vacancy.owner.id,),
            method=NotificationMethod.TEXT,
            text=_('Your vacancy has been moderated successfully'),
        )