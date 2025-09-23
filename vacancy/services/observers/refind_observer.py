from types import SimpleNamespace
from typing import Any

from service.broadcast_service import TelegramBroadcastService
from service.notifications import NotificationMethod
from service.notifications_impl import TelegramNotifier
from service.telegram_markup_factory import channel_vacancy_reply_markup, admin_vacancy_reply_markup
from telegram.handlers.bot_instance import bot
from telegram.models import Channel
from telegram.service.message_delete import MessageDeleteService, MessageDeleter
from .publisher import Observer
from ..vacancy_formatter import VacancyTelegramTextFormatter
from ...choices import STATUS_CLOSED


class VacancyRefindChannelObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data['vacancy']
        if vacancy.status != STATUS_CLOSED:
            channel = Channel.objects.filter(
                city=vacancy.owner.work_profile.city,
                is_active=True,
                has_bot_administrator=True,
                invite_link__isnull=False,
            ).first()

            deleter = MessageDeleter(bot)
            service = MessageDeleteService(deleter)
            service.delete_in_channel_by_vacancy(vacancy)

            self.notifier.notify(
                recipient=SimpleNamespace(chat_id=channel.id,),
                method=NotificationMethod.TEXT,
                text=VacancyTelegramTextFormatter(vacancy).for_channel(),
                reply_markup=channel_vacancy_reply_markup(vacancy),
                vacancy=vacancy,
            )

class VacancyRefindAdminObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data['vacancy']
        broadcast_service = TelegramBroadcastService(notifier=self.notifier)
        broadcast_service.admin_broadcast(
            method=NotificationMethod.TEXT,
            text=VacancyTelegramTextFormatter(vacancy).for_admin_refind(),
            reply_markup=admin_vacancy_reply_markup(vacancy),
        )