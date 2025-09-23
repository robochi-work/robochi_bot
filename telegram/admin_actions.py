from django.contrib import admin, messages
from django.core.handlers.wsgi import WSGIRequest
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from service.notifications import NotificationMethod
from service.telegram_strategy_factory import TelegramStrategyFactory
from telegram.handlers.bot_instance import bot
from telegram.models import Group, GroupMessage, Channel, ChannelMessage
from telegram.service.channel import ChannelService
from telegram.service.group import GroupService
from telegram.service.message_delete import MessageDeleter, MessageDeleteService, DeleteStats
from vacancy.services.vacancy_formatter import VacancyTelegramTextFormatter


def display_delete_stats(request: WSGIRequest, stats: DeleteStats) -> None:
    if stats['deleted']:
        messages.success(request, _('✅ Deleted: %(count)s message(s).') % {'count': stats['deleted']})
    if stats['failed']:
        messages.warning(request, _('⚠️ Failed to delete: %(count)s message(s).') % {'count': stats['failed']})
    if stats['total'] == 0:
        messages.info(request, _('ℹ️ No messages to delete.'))


@admin.action(description=_('Delete messages in Telegram'))
def delete_messages_by_group_action(modeladmin, request: WSGIRequest, queryset: QuerySet[Group]):
    deleter = MessageDeleter(bot)
    service = MessageDeleteService(deleter)
    stats = service.delete_by_groups(queryset)

    display_delete_stats(request=request, stats=stats)


@admin.action(description=_('Delete messages in Telegram'))
def delete_messages_action(modeladmin, request: WSGIRequest, queryset: QuerySet[GroupMessage]):
    deleter = MessageDeleter(bot)
    service = MessageDeleteService(deleter)
    stats = service.delete_messages(queryset)

    display_delete_stats(request=request, stats=stats)

@admin.action(description=_('Update group invite link'))
def update_group_invite_link(modeladmin, request: WSGIRequest, queryset: QuerySet[Group]):
    for group in queryset:
        updated_group = GroupService.update_invite_link(group=group)
        if updated_group:
            messages.success(request, _('Updated invite link'))
        else:
            messages.warning(request, _('⚠️ Failed to update invite link in %(group)s') % {'group': group.title})


@admin.action(description=_('Update channel invite link'))
def update_channel_invite_link(modeladmin, request: WSGIRequest, queryset: QuerySet[Channel]):
    for channel in queryset:
        updated_channel = ChannelService.update_invite_link(channel=channel)
        if updated_channel:
            messages.success(request, _('Updated invite link'))
        else:
            messages.warning(request, _('⚠️ Failed to update invite link in %(channel)s') % {'channel': channel.title})

@admin.action(description=_('Kick users from groups'))
def kick_group_users(modeladmin, request: WSGIRequest, queryset: QuerySet[Group]):
    for group in queryset:
        GroupService.kick_all_users(group=group)

@admin.action(description=_('Set default permissions'))
def set_default_permissions(modeladmin, request: WSGIRequest, queryset: QuerySet[Group]):
    for group in queryset:
        GroupService.set_default_permissions(group=group)
