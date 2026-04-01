from telegram.models import Channel


class ChannelService:
    @classmethod
    def update_invite_link(cls, channel: Channel, creates_join_request: bool = False) -> Channel:
        """Read the existing primary invite link from Telegram (do NOT create a new one)."""
        from telegram.handlers.bot_instance import bot

        chat = bot.get_chat(channel.id)
        if chat.invite_link:
            channel.invite_link = chat.invite_link
            channel.save(update_fields=["invite_link"])
        return channel
