from telebot.types import ChatMemberUpdated
from telegram.models import Group, Channel
from telegram.handlers.bot_instance import bot


@bot.my_chat_member_handler(func=lambda event: event.chat.type in ['channel'])
def channel_handle_bot_added(event: ChatMemberUpdated):
    channel, created = Channel.objects.update_or_create(
        id=event.chat.id,
        defaults={
            'title': event.chat.title or '',
            'is_active': False,
        }
    )

    status = event.new_chat_member.status
    if status in ['administrator',]:
        channel.has_bot_administrator = True

        if not channel.invite_link:
            try:
                invite = bot.create_chat_invite_link(chat_id=channel.id, creates_join_request=False)
                channel.invite_link = invite.invite_link
            except Exception:
                ...
    else:
        channel.has_bot_administrator = False
        channel.invite_link = None

    channel.save(update_fields=['has_bot_administrator', 'invite_link'])