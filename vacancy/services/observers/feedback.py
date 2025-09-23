from typing import Any

from service.broadcast_service import TelegramBroadcastService
from service.notifications import NotificationMethod
from service.notifications_impl import TelegramNotifier
from service.telegram_markup_factory import admin_vacancy_feedback_reply_markup

from .publisher import Observer
from ..vacancy_formatter import VacancyTelegramTextFormatter


class VacancyFeedbackAdminObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data.get('vacancy')
        feedback = data.get('feedback')
        if vacancy and feedback:

            broadcast_service = TelegramBroadcastService(notifier=self.notifier)
            broadcast_service.admin_broadcast(
                method=NotificationMethod.TEXT,
                text=VacancyTelegramTextFormatter(vacancy).for_admin_new_feedback(feedback),
                reply_markup=admin_vacancy_feedback_reply_markup(feedback),
            )
