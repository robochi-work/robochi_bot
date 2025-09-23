from telegram.handlers.bot_instance import bot
from telegram.models import Channel



class ChannelService:

    @classmethod
    def update_invite_link(cls, channel: Channel, creates_join_request:bool=False) -> Channel:
        invite = bot.create_chat_invite_link(chat_id=channel.id, creates_join_request=creates_join_request)
        channel.invite_link = invite.invite_link
        channel.save(update_fields=['invite_link'])
        return channel
