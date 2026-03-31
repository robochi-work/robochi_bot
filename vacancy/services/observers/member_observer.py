from typing import Any

import sentry_sdk

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
    """When group is full: edit channel message to 'Вакансію закрито', set search_active=False."""

    def __init__(self, notifier: TelegramNotifier | None = None):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data["vacancy"]

        if (
            vacancy.group.user_links
            and vacancy.group.user_links.filter(status=Status.MEMBER.value).count() >= vacancy.people_count
        ):
            # Turn off search flag
            vacancy.search_active = False
            vacancy.save(update_fields=["search_active"])

            text = VacancyTelegramTextFormatter(vacancy).for_channel(status="full")
            channel_message = (
                ChannelMessage.objects.filter(
                    channel_id=vacancy.channel.id,
                    extra__vacancy_id=vacancy.id,
                )
                .order_by("-id")
                .first()
            )

            if channel_message:
                strategy = TelegramStrategyFactory.get_strategy(NotificationMethod.TEXT)
                strategy.update(bot, vacancy.channel.id, text=text, message_id=channel_message.message_id)


class VacancySlotFreedObserver(Observer):
    """When worker leaves group: republish immediately with button, set search_active=True."""

    def __init__(self, notifier: TelegramNotifier | None = None):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy: Vacancy = data["vacancy"]

        # Only republish if vacancy is not closed
        from vacancy.choices import STATUS_ACTIVE, STATUS_APPROVED

        if vacancy.status not in [STATUS_APPROVED, STATUS_ACTIVE]:
            return

        current_count = vacancy.members.count()
        if current_count < vacancy.people_count:
            # Turn on search flag
            vacancy.search_active = True
            vacancy.save(update_fields=["search_active"])

            # Immediate republish with button
            try:
                channel_message = (
                    ChannelMessage.objects.filter(
                        channel_id=vacancy.channel.id,
                        extra__vacancy_id=vacancy.id,
                    )
                    .order_by("-id")
                    .first()
                )
                if channel_message:
                    MessageDeleter(bot_instance=bot).delete_message(channel_message)
            except Exception:
                sentry_sdk.capture_exception()
            VacancyApprovedChannelObserver(telegram_notifier).update("VACANCY_SLOT_FREED", data={"vacancy": vacancy})
