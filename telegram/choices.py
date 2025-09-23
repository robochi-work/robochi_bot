from django.db import models
from django.utils.translation import gettext_lazy as _


class Status(models.TextChoices):
    CREATOR = 'creator', _('Creator')
    ADMINISTRATOR = 'administrator', _('Administrator')
    OWNER = 'owner', _('Owner')
    MEMBER = 'member', _('Member')
    RESTRICTED = 'restricted', _('Restricted')
    LEFT = 'left', _('Left')
    KICKED = 'kicked', _('Kicked')
    BAN = 'ban', _('Ban')
    UNBAN = 'unban', _('Unban')

class CallStatus(models.TextChoices):
    CREATED = 'created', _('Created')
    SENT = 'sent', _('Sent')
    CONFIRM = 'confirm', _('Confirm')
    REJECT = 'reject', _('Reject')

class CallType(models.TextChoices):
    BEFORE_START = 'before_start', _('Before start')
    START = 'start', _('Start')
    AFTER_START = 'after_start', _('After start')


class MessageStatus(models.TextChoices):
    RECEIVED = 'received', _('Received')
    DELETED = 'deleted', _('Deleted')
    DELETE_FAILED = 'delete_failed', _('Delete failed')


STATUS_AVAILABLE = 'available'
STATUS_PROCESS = 'process'
STATUS_CHOICES = [
    (STATUS_AVAILABLE, _('Available')),
    (STATUS_PROCESS, _('Process')),
]

