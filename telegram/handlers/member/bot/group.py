import sentry_sdk
from telebot.types import ChatMemberUpdated

from telegram.handlers.bot_instance import bot
from telegram.models import Group


@bot.my_chat_member_handler(func=lambda event: event.chat.type in ["supergroup"])
def group_handle_bot_added(event: ChatMemberUpdated):
    group, created = Group.objects.update_or_create(
        id=event.chat.id,
        defaults={
            "title": event.chat.title or "",
        },
    )

    status = event.new_chat_member.status
    if status in ["administrator"]:
        group.has_bot_administrator = True

        if not group.invite_link:
            try:
                chat = bot.get_chat(event.chat.id)
                if chat.invite_link:
                    group.invite_link = chat.invite_link
            except Exception:
                sentry_sdk.capture_exception()
    else:
        group.has_bot_administrator = False
        group.invite_link = None

    group.save(
        update_fields=[
            "has_bot_administrator",
            "invite_link",
        ]
    )
