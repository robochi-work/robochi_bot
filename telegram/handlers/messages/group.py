import datetime

from django.conf import settings
from telebot import types

from telegram.choices import MessageStatus
from telegram.handlers.bot_instance import bot
from telegram.models import Group, GroupMessage
from user.models import User


@bot.message_handler(func=lambda message: message.chat.type in ['supergroup'], content_types=settings.TELEGRAM_BOT_ALL_GROUP_CONTENT_TYPES)
def handle_all_messages(message: types.Message):
    group = Group.objects.get(id=message.chat.id)
    content = {}
    match message.content_type:
        case 'text':
            content['text'] = message.text

    telegram_dt = datetime.datetime.fromtimestamp(message.date, tz=datetime.timezone.utc)

    group_message = GroupMessage(
        group=group,
        user_id=message.from_user.id,
        content_type=message.content_type,
        content=content,
        message_id=message.message_id,
        created_at=telegram_dt,
    )


    if message.content_type in ['new_chat_members', 'left_chat_member',]:
        bot.delete_message(
            chat_id=message.chat.id,
            message_id=message.message_id,
        )
        group_message.status = MessageStatus.DELETED

    group_message.save()