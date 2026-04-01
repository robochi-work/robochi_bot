import logging
from types import SimpleNamespace
from typing import Any

from service.notifications import NotificationMethod
from service.notifications_impl import TelegramNotifier
from service.telegram_markup_factory import channel_vacancy_reply_markup
from telegram.handlers.bot_instance import bot
from telegram.service.message_delete import MessageDeleter, MessageDeleteService

from ...choices import STATUS_CLOSED
from ..vacancy_formatter import VacancyTelegramTextFormatter
from .publisher import Observer

logger = logging.getLogger(__name__)


class VacancyApprovedChannelObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data["vacancy"]
        # Skip channel publish for renewal — workers are already in the group;
        # VacancyRenewalWorkersObserver sends the poll instead.
        if vacancy.extra.get("pending_worker_renewal"):
            return
        if vacancy.status != STATUS_CLOSED:
            channel = vacancy.channel

            deleter = MessageDeleter(bot)
            service = MessageDeleteService(deleter)
            service.delete_in_channel_by_vacancy(vacancy)

            self.notifier.notify(
                recipient=SimpleNamespace(
                    chat_id=channel.id,
                ),
                method=NotificationMethod.TEXT,
                text=VacancyTelegramTextFormatter(vacancy).for_channel(),
                reply_markup=channel_vacancy_reply_markup(vacancy),
                vacancy=vacancy,
            )
            logger.info("vacancy_published", extra={"vacancy_id": vacancy.id, "channel_id": channel.id})

            # Activate search flag
            vacancy.search_active = True
            vacancy.save(update_fields=["search_active"])
