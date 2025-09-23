from typing import TypedDict, Iterable
from django.db.models import QuerySet
from telebot import TeleBot

from telegram.models import GroupMessage, MessageStatus, Group, ChannelMessage
import logging

from vacancy.models import Vacancy

logger = logging.getLogger(__name__)

class MessageDeleter:
    def __init__(self, bot_instance: TeleBot):
        self.bot = bot_instance

    def delete_message(self, message: GroupMessage | ChannelMessage) -> bool:
        try:
            instance = getattr(message, 'group', getattr(message, 'channel', None))
            if not instance:
                raise AttributeError(f'Message #{getattr(message, "id")} does not contain a group or channel')

            self.bot.delete_message(
                chat_id=instance.id,
                message_id=message.message_id
            )
            message.status = MessageStatus.DELETED
            message.save(update_fields=["status"])
            return True

        except Exception as e:
            logger.warning(f"Error deleting message {message.message_id}: {e}")
            message.status = MessageStatus.DELETE_FAILED
            message.save(update_fields=["status"])
            return False

class DeleteStats(TypedDict):
    total: int
    deleted: int
    failed: int

class MessageDeleteService:
    def __init__(self, deleter: MessageDeleter):
        self.deleter = deleter

    def delete_messages(self, queryset: QuerySet[GroupMessage | ChannelMessage]) -> DeleteStats:
        deleted = 0
        failed = 0

        for msg in queryset:
            success = self.deleter.delete_message(msg)
            if success:
                deleted += 1
            else:
                failed += 1

        return {
            'total': queryset.count(),
            'deleted': deleted,
            'failed': failed,
        }

    def delete_by_groups(self, groups: Iterable[Group]) -> DeleteStats:
        messages = GroupMessage.objects.filter(
            group__in=groups,
            status__in=[MessageStatus.RECEIVED, MessageStatus.DELETE_FAILED]
        )
        return self.delete_messages(messages)

    def delete_in_channel_by_vacancy(self, vacancy: Vacancy) -> DeleteStats:
        messages = ChannelMessage.objects.filter(
            status__in=[MessageStatus.RECEIVED, MessageStatus.DELETE_FAILED],
            extra__vacancy_id=vacancy.id,
        )
        return self.delete_messages(messages)

    def delete_in_group_by_vacancy(self, vacancy: Vacancy) -> DeleteStats:
        messages = GroupMessage.objects.filter(
            status__in=[MessageStatus.RECEIVED, MessageStatus.DELETE_FAILED],
            extra__vacancy_id=vacancy.id,
        )
        return self.delete_messages(messages)