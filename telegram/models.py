from django.db import models
from django.utils.translation import gettext_lazy as _
from telegram.choices import MessageStatus, Status, STATUS_CHOICES, STATUS_AVAILABLE, CallStatus, CallType


class Chat(models.Model):
    id = models.BigIntegerField(primary_key=True, verbose_name=_('ID'))
    title = models.CharField(_('title'), max_length=255, null=True, blank=True)
    is_active = models.BooleanField(_('is active'), default=False)

    class Meta:
        abstract = True
        verbose_name = _("Chat")
        verbose_name_plural = _("Chats")

class Channel(Chat):
    city = models.ForeignKey('city.City', on_delete=models.SET_NULL, null=True, verbose_name=_('City'))
    has_bot_administrator = models.BooleanField(_('has bot administrator'), default=False)
    invite_link = models.URLField(_('Invite link'), null=True, blank=True)

    class Meta:
        verbose_name = _("Channel")
        verbose_name_plural = _("Channels")

class ChannelMessage(models.Model):
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name='messages', verbose_name=_('Channel'))
    content_type = models.CharField(max_length=32, verbose_name=_('Content type'))
    message_id = models.BigIntegerField(verbose_name=_('Message ID'))
    content = models.JSONField(null=True, blank=True, verbose_name=_('Content'))
    status = models.CharField(
        max_length=20,
        choices=MessageStatus.choices,
        default=MessageStatus.RECEIVED,
        verbose_name=_('Status')
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created at'))
    extra = models.JSONField(blank=True, default=dict)

    def __str__(self):
        return f"{self.channel.title} [{self.message_id}]"

    class Meta:
        verbose_name = _("Channel message")
        verbose_name_plural = _("Channel messages")

class Group(Chat):
    has_bot_administrator = models.BooleanField(_('has bot administrator'), default=False)
    users = models.ManyToManyField(
        'user.User',
        through='UserInGroup',
        related_name='telegram_users',
        verbose_name=_('Users')
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_AVAILABLE,
        verbose_name=_('Status')
    )
    invite_link = models.URLField(_('Invite link'), null=True, blank=True)

    def __str__(self):
        return f"Group: {self.title}"

    class Meta:
        verbose_name = _("Group")
        verbose_name_plural = _("Groups")

class GroupMessage(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='messages', verbose_name=_('Group'))
    user_id = models.BigIntegerField(null=True, blank=True, verbose_name=_('User ID'))
    content_type = models.CharField(max_length=32, verbose_name=_('Content type'))
    message_id = models.BigIntegerField(verbose_name=_('Message ID'))
    content = models.JSONField(null=True, blank=True, verbose_name=_('Content'))
    status = models.CharField(
        max_length=20,
        choices=MessageStatus.choices,
        default=MessageStatus.RECEIVED,
        verbose_name=_('Status')
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created at'))
    extra = models.JSONField(blank=True, default=dict)

    def __str__(self):
        return f"{self.group.title}"

    class Meta:
        verbose_name = _("Group message")
        verbose_name_plural = _("Group messages")

class UserInGroup(models.Model):
    user = models.ForeignKey('user.User', on_delete=models.CASCADE, verbose_name=_('User'))
    group = models.ForeignKey('Group', on_delete=models.CASCADE, related_name='user_links', verbose_name=_('Group'))
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.MEMBER,
        verbose_name=_('Status')
    )

    class Meta:
        unique_together = ('user', 'group')
        verbose_name = _("User in group")
        verbose_name_plural = _("User in groups")


