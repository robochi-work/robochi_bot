from telebot.types import ChatMemberUpdated

from telegram.handlers.bot_instance import bot
from telegram.models import Channel


@bot.my_chat_member_handler(func=lambda event: event.chat.type in ["channel"])
def channel_handle_bot_added(event: ChatMemberUpdated):
    channel, created = Channel.objects.update_or_create(
        id=event.chat.id,
        defaults={
            "title": event.chat.title or "",
            "is_active": False,
        },
    )

    status = event.new_chat_member.status
    if status in ["administrator"]:
        channel.has_bot_administrator = True
    else:
        channel.has_bot_administrator = False

    channel.save(update_fields=["has_bot_administrator"])
