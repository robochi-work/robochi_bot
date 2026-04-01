from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from parler.admin import TranslatableAdmin

from telegram.admin_actions import update_channel_invite_link
from telegram.models import Channel

from .models import City


@admin.register(City)
class CityAdmin(TranslatableAdmin):
    list_display = ("name",)


class ChannelProxy(Channel):
    class Meta:
        proxy = True
        app_label = "city"
        verbose_name = _("Channel")
        verbose_name_plural = _("Channels")


@admin.register(ChannelProxy)
class ChannelInCityAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "is_active",
        "city",
    )
    readonly_fields = (
        "id",
        "title",
    )
    actions = [update_channel_invite_link]

    def has_add_permission(self, request):
        return False
