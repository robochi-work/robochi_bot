from django.contrib import admin
from django.utils.translation import gettext as _
from telegram.admin_actions import delete_messages_by_group_action, delete_messages_action, update_group_invite_link, \
    kick_group_users, set_default_permissions, update_channel_invite_link
from telegram.models import Group, UserInGroup, GroupMessage, Channel, ChannelMessage


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'status', 'is_active', 'has_bot_administrator','is_configured')
    readonly_fields = ('id', 'title',)
    actions = [delete_messages_by_group_action, update_group_invite_link, kick_group_users, set_default_permissions]

    @admin.display(description=_('Configured'), boolean=True)
    def is_configured(self, obj: Group) -> bool:
        return all([obj.is_active, obj.has_bot_administrator, obj.invite_link, str(obj.id).startswith('-100')])


@admin.register(UserInGroup)
class UserInGroupAdmin(admin.ModelAdmin):
    list_display = ('user', 'group', 'status',)


@admin.register(GroupMessage)
class GroupMessageAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'group', 'content_type', 'content', 'status',)
    actions = [delete_messages_action]

@admin.register(ChannelMessage)
class ChannelMessageAdmin(admin.ModelAdmin):
    list_display = ('display_channel', 'content_type', 'status', 'created_at')
    actions = [delete_messages_action]

    @admin.display(description=_('Message'))
    def display_channel(self, obj: ChannelMessage):
        return obj.channel.title


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'city',)
    readonly_fields = ('id', 'title',)
    actions = [update_channel_invite_link]
