from datetime import datetime
from types import SimpleNamespace
from typing import Any, Optional

from django.utils import timezone

from service.notifications import NotificationMethod
from service.notifications_impl import TelegramNotifier
from service.telegram_strategy_factory import TelegramStrategyFactory
from telegram.choices import Status
from telegram.handlers.bot_instance import bot
from telegram.models import ChannelMessage
from telegram.service.message_delete import MessageDeleter
from vacancy.models import Vacancy
from vacancy.services.observers.approved_channel_observer import VacancyApprovedChannelObserver
from vacancy.services.observers.publisher import Observer
from vacancy.services.vacancy_formatter import VacancyTelegramTextFormatter


telegram_notifier = TelegramNotifier(bot)

class VacancyIsFullObserver(Observer):
    def __init__(self, notifier: Optional[TelegramNotifier] = None):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data['vacancy']

        if vacancy.group.user_links and vacancy.group.user_links.filter(status=Status.MEMBER.value).count() >= vacancy.people_count:
            text = VacancyTelegramTextFormatter(vacancy).for_channel(status='full')
            channel_message = ChannelMessage.objects.filter(
                channel_id=vacancy.channel.id,
                extra__vacancy_id=vacancy.id,
            ).order_by('-id').first()

            strategy = TelegramStrategyFactory.get_strategy(NotificationMethod.TEXT)
            message = strategy.update(bot, vacancy.channel.id, text=text, message_id=channel_message.message_id)


class VacancySlotFreedObserver(Observer):
    def __init__(self, notifier: Optional[TelegramNotifier] = None):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy: Vacancy = data['vacancy']
        start_naive = datetime.combine(vacancy.date, vacancy.start_time)
        start_aware = timezone.make_aware(start_naive, timezone.get_current_timezone())

        if timezone.now() < start_aware:
            current_count = vacancy.members.count()
            if current_count == vacancy.people_count - 1:
                try:
                    channel_message = ChannelMessage.objects.filter(content__channel_id=vacancy.channel.id, extra__vacancy_id=vacancy.id,).order_by('-id').first()
                    MessageDeleter(bot_instance=bot).delete_message(channel_message)
                except:
                    pass
                VacancyApprovedChannelObserver(telegram_notifier).update('VACANCY_SLOT_FREED', data={'vacancy': vacancy, })
