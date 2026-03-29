import logging
from types import SimpleNamespace
from typing import Iterable
from datetime import timedelta

from django.utils import timezone
from celery import shared_task

from service.notifications import NotificationMethod
from service.notifications_impl import TelegramNotifier
from service.telegram_markup_factory import channel_vacancy_reply_markup
from telegram.handlers.bot_instance import bot
from telegram.service.message_delete import MessageDeleter, MessageDeleteService
from vacancy.choices import STATUS_ACTIVE, STATUS_APPROVED
from vacancy.models import Vacancy
from vacancy.services.vacancy_formatter import VacancyTelegramTextFormatter

logger = logging.getLogger(__name__)


def resend_vacancy_to_channel(vacancy: Vacancy):
    """Delete old message and republish vacancy with button."""
    channel = vacancy.channel
    if not channel:
        return

    deleter = MessageDeleter(bot)
    service = MessageDeleteService(deleter)
    service.delete_in_channel_by_vacancy(vacancy)

    TelegramNotifier(bot).notify(
        recipient=SimpleNamespace(chat_id=channel.id),
        method=NotificationMethod.TEXT,
        text=VacancyTelegramTextFormatter(vacancy).for_channel(),
        reply_markup=channel_vacancy_reply_markup(vacancy),
        vacancy=vacancy,
    )


@shared_task
def resend_vacancies_to_channel_task():
    """Rotation: republish vacancies with active search button every 5 minutes."""
    vacancies = Vacancy.objects.filter(
        status__in=[STATUS_APPROVED, STATUS_ACTIVE],
        search_active=True,
    )

    for vacancy in vacancies:
        try:
            message = vacancy.last_channel_message
            # Only republish if 5+ minutes since last publication (or no message)
            if message and message.created_at >= timezone.now() - timedelta(minutes=5):
                continue

            resend_vacancy_to_channel(vacancy)
        except Exception as e:
            logger.warning(f'Error in rotation for vacancy {vacancy.id}: {e}')
