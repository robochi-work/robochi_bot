import logging

from django.contrib import messages
from telebot import TeleBot

from telegram.choices import MessageStatus
from telegram.models import ChannelMessage, Channel, Group, GroupMessage
from .notifications import Notifier, NotificationMethod
from .telegram_strategy_factory import TelegramStrategyFactory


class DjangoMessagesNotifier(Notifier):

    def notify(self, recipient, method: NotificationMethod, **kwargs):
        text = kwargs.get('text') or kwargs.get('content', '')
        level = kwargs.get('level', 'info')
        funcs = {
            'success': messages.success,
            'info': messages.info,
            'warning': messages.warning,
            'error': messages.error,
        }
        func = funcs.get(level)
        if not func:
            raise ValueError(f'Unknown message level: {level}')
        func(recipient, text)


class TelegramNotifier(Notifier):
    def __init__(self, bot: TeleBot):
        self.bot = bot

    def notify(self, recipient, method: NotificationMethod = NotificationMethod.TEXT, **kwargs):
        chat_id = getattr(recipient, 'chat_id', None)
        is_update = kwargs.pop('is_update', False)
        vacancy = kwargs.pop('vacancy', None)

        if chat_id:
            strategy = TelegramStrategyFactory.get_strategy(method)

            strategy_method = getattr(strategy, 'send' if not is_update else 'update')

            try:
                message = strategy_method(self.bot, chat_id, **kwargs)
            except Exception as e:
                logging.warning('Telegram notification failed: %s', e)
                return

            if message:
                try:
                    channel = Channel.objects.get(id=chat_id)

                    content = {
                        'channel_id': channel.id,
                    }
                    match message.content_type:
                        case 'text':
                            content['text'] = message.text

                    new_message = ChannelMessage.objects.create(
                        channel=channel,
                        content_type=message.content_type,
                        message_id=message.message_id,
                        content=content,
                        status=MessageStatus.RECEIVED,
                        extra={'vacancy_id': vacancy.id} if vacancy else None,
                    )
                    ...
                except Exception as ex:
                    try:
                        group = Group.objects.get(id=chat_id)
                        content = {
                            'text': message.text or '',
                        }
                        new_message = GroupMessage.objects.create(
                            group=group,
                            user_id=message.from_user.id,
                            content_type=message.content_type,
                            message_id=message.message_id,
                            content=content,
                            status=MessageStatus.RECEIVED,
                            extra={'vacancy_id': vacancy.id} if vacancy else None,
                        )
                    except Exception as ex:
                        ...
                finally:
                    ...
            else:
                raise ValueError('chat_id must be defined')
