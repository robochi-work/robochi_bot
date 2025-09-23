from types import SimpleNamespace
from typing import Any
from django.utils.translation import gettext as _
from service.notifications import NotificationMethod
from service.notifications_impl import TelegramNotifier, DjangoMessagesNotifier
from .publisher import Observer
from ..vacancy_formatter import VacancyTelegramTextFormatter


class VacancyCreatedUserObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data['vacancy']
        self.notifier.notify(
            recipient=SimpleNamespace(chat_id=vacancy.owner.id,),
            method=NotificationMethod.TEXT,
            text=VacancyTelegramTextFormatter(vacancy).for_creator_chat(),
        )


class VacancyCreatedUserDjangoObserver(Observer):
    def __init__(self, notifier: DjangoMessagesNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        request = data.get('request')

        if request:
            self.notifier.notify(
                recipient=request,
                method=NotificationMethod.TEXT,
                level='success',
                text=_('Your vacancy has been successfully created and sent for moderation!')
            )