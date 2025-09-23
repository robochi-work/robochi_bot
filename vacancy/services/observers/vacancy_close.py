import functools
import logging
from typing import Any
from service.broadcast_service import TelegramBroadcastService
from service.notifications_impl import TelegramNotifier
from telegram.choices import STATUS_AVAILABLE
from telegram.handlers.bot_instance import bot
from telegram.service.group import GroupService
from telegram.service.message_delete import MessageDeleter, MessageDeleteService
from vacancy.services.observers.publisher import Observer

from vacancy.choices import STATUS_CLOSED

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
        vacancy = data['vacancy']
        deleter = MessageDeleter(bot)
        service = MessageDeleteService(deleter)
        stats_group = service.delete_in_group_by_vacancy(vacancy)
        logging.info(f'Message deleted')

class VacancyDeleteMessagesChannelObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    @log_warn_on_exception
    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data['vacancy']
        deleter = MessageDeleter(bot)
        service = MessageDeleteService(deleter)
        stats_channel = service.delete_in_channel_by_vacancy(vacancy)
        logging.info(f'Message deleted')

class VacancyKickGroupUsersObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    @log_warn_on_exception
    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data['vacancy']
        if vacancy.group:
            GroupService.kick_all_users(group=vacancy.group)
            logging.info('kick users')
        else:
            logging.info('kick users fail - vacancy has no group')

class VacancyGroupFeeStatusObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    @log_warn_on_exception
    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data['vacancy']
        if vacancy.group:
            vacancy.group.status = STATUS_AVAILABLE
            vacancy.group.save(update_fields=['status'])

            vacancy.group = None
            vacancy.save(update_fields=['group'])

            logging.info(f'set vacancy group status - {STATUS_AVAILABLE}')

class VacancyStatusClosedObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    @log_warn_on_exception
    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data['vacancy']
        vacancy.status = STATUS_CLOSED
        vacancy.save(update_fields=['status'])
        logging.info(f'set vacancy status - {STATUS_CLOSED}')


class VacancyNotifyAdminsObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    @log_warn_on_exception
    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data['vacancy']
        broadcast_service = TelegramBroadcastService(notifier=self.notifier)
        broadcast_service.admin_broadcast(
            text='Вакансия закрыта',
        )
        logging.info('Notify admins - vacancy closed')

class VacancyPaymentDoesNotExistObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    @log_warn_on_exception
    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data['vacancy']
        broadcast_service = TelegramBroadcastService(notifier=self.notifier)
        broadcast_service.admin_broadcast(
            text=f'Вакансия не оплачена по истечению времени\n{vacancy.group.invite_link}',
        )
        logging.info('Notify admins - vacancy does not payment exists')
