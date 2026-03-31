import datetime
import re

import sentry_sdk
from django.conf import settings
from telebot import types

from telegram.choices import MessageStatus
from telegram.handlers.bot_instance import bot
from telegram.models import Group, GroupMessage
from user.models import User

# Phone number patterns for Ukraine
PHONE_PATTERNS = [
    re.compile(r"\+380\d{9}"),  # +380XXXXXXXXX (12 digits with +)
    re.compile(r"380\d{9}"),  # 380XXXXXXXXX (12 digits without +)
    re.compile(r"(?<!\d)0\d{9}(?!\d)"),  # 0XXXXXXXXX (10 digits starting with 0)
]


def contains_phone_number(text: str) -> bool:
    """Check if text contains a Ukrainian phone number."""
    if not text:
        return False
    # Remove spaces, dashes, parentheses for better matching
    cleaned = re.sub(r"[\s\-\(\)]", "", text)
    for pattern in PHONE_PATTERNS:
        if pattern.search(cleaned):
            return True
    return False


@bot.message_handler(
    func=lambda message: message.chat.type in ["supergroup"],
    content_types=settings.TELEGRAM_BOT_ALL_GROUP_CONTENT_TYPES,
)
def handle_all_messages(message: types.Message):
    group = Group.objects.get(id=message.chat.id)

    # Phone number filter: delete messages with phone numbers from non-admins
    if message.content_type == "text" and message.text:
        user_id = message.from_user.id
        try:
            user = User.objects.get(id=user_id)
            is_admin = user.is_staff
        except User.DoesNotExist:
            is_admin = False

        if not is_admin and contains_phone_number(message.text):
            try:
                bot.delete_message(
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                )
                bot.send_message(
                    message.from_user.id,
                    "Ваше повідомлення видалено. Заборонено надсилати номери телефонів у групі вакансії.",
                )
            except Exception:
                sentry_sdk.capture_exception()
            return

    content = {}
    match message.content_type:
        case "text":
            content["text"] = message.text

    telegram_dt = datetime.datetime.fromtimestamp(message.date, tz=datetime.UTC)
    group_message = GroupMessage(
        group=group,
        user_id=message.from_user.id,
        content_type=message.content_type,
        content=content,
        message_id=message.message_id,
        created_at=telegram_dt,
    )

    if message.content_type in [
        "new_chat_members",
        "left_chat_member",
    ]:
        bot.delete_message(
            chat_id=message.chat.id,
            message_id=message.message_id,
        )
        group_message.status = MessageStatus.DELETED
