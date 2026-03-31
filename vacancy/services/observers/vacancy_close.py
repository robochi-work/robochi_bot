import functools
import logging
from typing import Any

from service.broadcast_service import TelegramBroadcastService
from service.notifications_impl import TelegramNotifier
from telegram.choices import STATUS_AVAILABLE
from telegram.handlers.bot_instance import bot
from telegram.service.group import GroupService
from telegram.service.message_delete import MessageDeleter, MessageDeleteService
from vacancy.choices import STATUS_CLOSED
from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter
from vacancy.services.observers.publisher import Observer


def log_warn_on_exception(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logging.warning(f"Exception occurred in {func.__name__}: {e}", exc_info=True)
            raise

    return wrapper


class VacancyDeleteMessagesObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    @log_warn_on_exception
    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data["vacancy"]
        deleter = MessageDeleter(bot)
        service = MessageDeleteService(deleter)
        service.delete_in_group_by_vacancy(vacancy)
        logging.info("Message deleted")


class VacancyDeleteMessagesChannelObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    @log_warn_on_exception
    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data["vacancy"]
        # Edit channel message to "Вакансію закрито" instead of deleting
        if vacancy.channel:
            try:
                from service.notifications import NotificationMethod
                from service.telegram_strategy_factory import TelegramStrategyFactory
                from telegram.models import ChannelMessage
                from vacancy.services.vacancy_formatter import VacancyTelegramTextFormatter

                channel_message = (
                    ChannelMessage.objects.filter(
                        channel_id=vacancy.channel.id,
                        extra__vacancy_id=vacancy.id,
                    )
                    .order_by("-id")
                    .first()
                )

                if channel_message:
                    text = VacancyTelegramTextFormatter(vacancy).for_channel(status="full")
                    strategy = TelegramStrategyFactory.get_strategy(NotificationMethod.TEXT)
                    strategy.update(bot, vacancy.channel.id, text=text, message_id=channel_message.message_id)
                    logging.info(f"Channel message edited to closed for vacancy {vacancy.id}")
                else:
                    logging.info(f"No channel message found for vacancy {vacancy.id}")
            except Exception as e:
                logging.warning(f"Failed to edit channel message for vacancy {vacancy.id}: {e}")
        else:
            logging.info(f"Vacancy {vacancy.id} has no channel")


class VacancyKickGroupUsersObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    @log_warn_on_exception
    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data["vacancy"]
        if vacancy.group:
            GroupService.kick_all_users(group=vacancy.group)
            logging.info("kick users")
        else:
            logging.info("kick users fail - vacancy has no group")


class VacancyGroupFeeStatusObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    @log_warn_on_exception
    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data["vacancy"]
        if vacancy.group:
            vacancy.group.status = STATUS_AVAILABLE
            vacancy.group.save(update_fields=["status"])

            vacancy.group = None
            vacancy.save(update_fields=["group"])

            logging.info(f"set vacancy group status - {STATUS_AVAILABLE}")


class VacancyStatusClosedObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    @log_warn_on_exception
    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data["vacancy"]
        vacancy.status = STATUS_CLOSED
        vacancy.search_active = False
        vacancy.save(update_fields=["status", "search_active"])
        logging.info(f"set vacancy status - {STATUS_CLOSED}, search_active=False")

        # Edit channel message: remove button, show "Вакансію закрито"
        if vacancy.channel:
            try:
                from service.notifications import NotificationMethod
                from service.telegram_strategy_factory import TelegramStrategyFactory
                from telegram.models import ChannelMessage
                from vacancy.services.vacancy_formatter import VacancyTelegramTextFormatter

                channel_message = (
                    ChannelMessage.objects.filter(
                        channel_id=vacancy.channel.id,
                        extra__vacancy_id=vacancy.id,
                    )
                    .order_by("-id")
                    .first()
                )

                if channel_message:
                    text = VacancyTelegramTextFormatter(vacancy).for_channel(status="full")
                    strategy = TelegramStrategyFactory.get_strategy(NotificationMethod.TEXT)
                    strategy.update(bot, vacancy.channel.id, text=text, message_id=channel_message.message_id)
                    logging.info(f"Channel message updated to closed for vacancy {vacancy.id}")
            except Exception as e:
                logging.warning(f"Failed to update channel message for vacancy {vacancy.id}: {e}")


class VacancyNotifyAdminsObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    @log_warn_on_exception
    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data["vacancy"]
        broadcast_service = TelegramBroadcastService(notifier=self.notifier)
        broadcast_service.admin_broadcast(
            text=CallVacancyTelegramTextFormatter(vacancy).vacancy_closed_admin(),
        )
        logging.info("Notify admins - vacancy closed")


class VacancyPaymentDoesNotExistObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    @log_warn_on_exception
    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data["vacancy"]
        broadcast_service = TelegramBroadcastService(notifier=self.notifier)
        broadcast_service.admin_broadcast(
            text=CallVacancyTelegramTextFormatter(vacancy).vacancy_payment_no_exist_admin(),
        )
        logging.info("Notify admins - vacancy does not payment exists")
