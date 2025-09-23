from telebot.types import ChatMemberUpdated
from telegram.models import Group
from telegram.handlers.bot_instance import bot
from telegram.service.group import GroupService


@bot.my_chat_member_handler(func=lambda event: event.chat.type in ['supergroup'])
def group_handle_bot_added(event: ChatMemberUpdated):
    group, created = Group.objects.update_or_create(
        id=event.chat.id,
        defaults={
            'title': event.chat.title or '',
        }
    )

    status = event.new_chat_member.status
    if status in ['administrator',]:
        group.has_bot_administrator = True

        if not group.invite_link:
            try:
                GroupService.update_invite_link(group=group)
            except Exception:
                ...
    else:
        group.has_bot_administrator = False
        group.invite_link = None

    group.save(update_fields=['has_bot_administrator',])