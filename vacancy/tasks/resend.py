import logging
from types import SimpleNamespace

from celery import shared_task
from django.utils import timezone

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
        logger.warning(f"Rotation skip: vacancy {vacancy.id} has no channel")
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
    logger.warning(f"Rotation: vacancy {vacancy.id} republished to channel {channel.id}")


@shared_task
def resend_vacancies_to_channel_task():
    """Rotation: republish vacancies with active search button every 5 minutes."""
    logger.info("task_started", extra={"task": "resend_vacancies_to_channel_task"})
    vacancies = Vacancy.objects.filter(
        status__in=[STATUS_APPROVED, STATUS_ACTIVE],
        search_active=True,
    )

    count = vacancies.count()
    if count > 0:
        logger.warning(f"Rotation check: {count} vacancies with search_active=True")

    for vacancy in vacancies:
        try:
            message = vacancy.last_channel_message
            now = timezone.now()

            if message:
                age = (now - message.created_at).total_seconds()
                logger.warning(f"Rotation: vacancy {vacancy.id} last_msg age={age:.0f}s")
                if age < 300:  # 5 minutes
                    continue
            else:
                logger.warning(f"Rotation: vacancy {vacancy.id} has no channel message")

            resend_vacancy_to_channel(vacancy)
        except Exception as e:
            logger.error("task_failed", extra={"task": "resend_vacancies_to_channel_task", "error": str(e)})
            logger.warning(f"Error in rotation for vacancy {vacancy.id}: {e}")
    logger.info("task_completed", extra={"task": "resend_vacancies_to_channel_task", "processed": count})
