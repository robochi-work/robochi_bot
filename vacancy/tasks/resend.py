import logging
from types import SimpleNamespace
from typing import Iterable
from datetime import datetime, timedelta

from django.db.models import QuerySet
from django.utils import timezone
from celery import shared_task

from service.notifications import NotificationMethod
from service.notifications_impl import TelegramNotifier
from service.telegram_markup_factory import channel_vacancy_reply_markup
from telegram.handlers.bot_instance import bot
from telegram.models import Channel
from telegram.service.message_delete import MessageDeleter, MessageDeleteService
from vacancy.choices import STATUS_ACTIVE, STATUS_APPROVED
from vacancy.models import Vacancy
from vacancy.services.vacancy_formatter import VacancyTelegramTextFormatter

Minutes = int
logger = logging.getLogger(__name__)


def get_active_vacancies() -> QuerySet[Vacancy]:
    vacancies = Vacancy.objects.filter(
        status__in=[STATUS_APPROVED, STATUS_ACTIVE],
    )
    return vacancies

def resend_vacancies_to_channel(vacancies: Iterable[Vacancy]):
    for vacancy in vacancies:
        channel = Channel.objects.get(
            city=vacancy.owner.work_profile.city,
            is_active=True,
            has_bot_administrator=True,
            invite_link__isnull=False,
        )

        deleter = MessageDeleter(bot)
        service = MessageDeleteService(deleter)
        service.delete_in_channel_by_vacancy(vacancy)

        TelegramNotifier(bot).notify(
            recipient=SimpleNamespace(chat_id=channel.id, ),
            method=NotificationMethod.TEXT,
            text=VacancyTelegramTextFormatter(vacancy).for_channel(),
            reply_markup=channel_vacancy_reply_markup(vacancy),
            vacancy=vacancy,
        )

@shared_task
def resend_vacancies_to_channel_task():
    vacancies = get_active_vacancies()

    naive_now = datetime.now()
    aware_now = timezone.make_aware(naive_now, timezone.get_current_timezone())
    filtered_vacancies = []
    for vacancy in vacancies:
        try:
            if vacancy.people_count > vacancy.members.count():
                message = vacancy.last_channel_message
                if (message and message.created_at < timezone.now() - timedelta(minutes=5)) or not message:

                    start_naive = datetime.combine(vacancy.date, vacancy.start_time)
                    start_aware = timezone.make_aware(start_naive, timezone.get_current_timezone())

                    if aware_now > start_aware:
                        if vacancy.extra.get('start_pre_call') == 'need':
                            filtered_vacancies.append(vacancy)
                    else:
                        filtered_vacancies.append(vacancy)
        except Exception as e:
            logger.warning(f'Error resending vacancies to channel: {e}')
            ...

    resend_vacancies_to_channel(filtered_vacancies)
