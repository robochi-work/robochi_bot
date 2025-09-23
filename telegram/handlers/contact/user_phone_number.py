from typing import Any
from django.utils.translation import gettext as _
from telebot import types
from telebot.types import ReplyKeyboardRemove

from telegram.handlers.bot_instance import bot
from telegram.handlers.messages.commands import start
from telegram.handlers.utils import user_required
from user.models import User


@bot.message_handler(content_types=['contact'])
@user_required
def contact(message: types.Message, user: User, **kwargs: dict[str, Any]) -> None:
    if message.contact and message.contact.phone_number:
        user.phone_number = f'+{message.contact.phone_number.lstrip('+')}'
        user.save(update_fields=['phone_number'])
        bot.delete_message(
            chat_id=message.chat.id,
            message_id=message.message_id,
        )
        bot.send_message(
            chat_id=message.chat.id,
            text=_('Phone number saved'),
            reply_markup=ReplyKeyboardRemove(),
        )
        start(message, user=user)