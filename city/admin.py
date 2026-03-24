from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from parler.admin import TranslatableAdmin
from telegram.models import Channel
from .models import City


class ChannelInline(admin.StackedInline):
    model = Channel
    extra = 0
    readonly_fields = ('id', 'title', 'has_bot_administrator')
    fields = ('id', 'title', 'is_active', 'has_bot_administrator', 'invite_link')
    can_delete = False
    max_num = 1


@admin.register(City)
class CityAdmin(TranslatableAdmin):
    list_display = ('name', 'get_channel_title', 'get_channel_status')
    inlines = [ChannelInline]

    @admin.display(description=_('Channel'))
    def get_channel_title(self, obj):
        channel = Channel.objects.filter(city=obj).first()
        return channel.title if channel else '-'

    @admin.display(description=_('Configured'), boolean=True)
    def get_channel_status(self, obj):
        channel = Channel.objects.filter(city=obj).first()
        if not channel:
            return False
        return all([channel.is_active, channel.has_bot_administrator, channel.invite_link])
