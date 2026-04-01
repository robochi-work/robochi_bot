from typing import Any

from service.broadcast_service import TelegramBroadcastService
from service.notifications import NotificationMethod
from service.notifications_impl import TelegramNotifier
from service.telegram_markup_factory import admin_vacancy_reply_markup
from vacancy.services.vacancy_formatter import VacancyTelegramTextFormatter

from .publisher import Observer


class VacancyCreatedAdminObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data["vacancy"]
        broadcast_service = TelegramBroadcastService(notifier=self.notifier)
        broadcast_service.admin_broadcast(
            method=NotificationMethod.TEXT,
            text=VacancyTelegramTextFormatter(vacancy).for_admin_chat(),
            reply_markup=admin_vacancy_reply_markup(vacancy),
        )
