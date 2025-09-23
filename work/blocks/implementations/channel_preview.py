from telegram.models import Channel
from work.blocks.base import PageBlock
from work.blocks.registry import block_registry


@block_registry.register
class ChannelPreviewBlock(PageBlock):
    order = 1

    def is_visible(self, request):
        return True

    def get_context(self, request):
        return {
            'channel': Channel.objects.filter(
                city=request.user.work_profile.city,
                is_active=True,
                has_bot_administrator=True,
                invite_link__isnull=False,
            ).first()
        }

    @property
    def template_name(self):
        return f'work/blocks/channel_preview.html'


