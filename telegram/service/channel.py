from telegram.models import Channel


class ChannelService:
    @classmethod
    def update_invite_link(cls, channel: Channel, creates_join_request: bool = False) -> Channel:
        """No-op: invite links are managed manually via Django admin, not by the bot."""
        return channel
