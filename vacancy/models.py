from typing import Optional

from django.db import models
from django.contrib.auth import get_user_model
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from telegram.choices import CallStatus, CallType, Status
from telegram.models import Group, Channel, ChannelMessage
from .choices import (
    DATE_CHOICES, GENDER_CHOICES, GENDER_ANY,
    PAYMENT_UNIT_CHOICES, STATUS_CHOICES, STATUS_PENDING, PAYMENT_SHIFT, PAYMENT_METHOD_CHOICES,
    PAYMENT_CASH, DATE_TODAY,
)
from .services.observers.events import VACANCY_DELETE, VACANCY_NEW_FEEDBACK

User = get_user_model()

class Vacancy(models.Model):
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='vacancies',
        verbose_name=_('Owner')
    )
    gender = models.CharField(
        max_length=1, choices=GENDER_CHOICES, default=GENDER_ANY, verbose_name=_('Preferred Gender')
    )
    people_count = models.PositiveIntegerField(verbose_name=_('Number of People'))
    has_passport = models.BooleanField(verbose_name=_('Has Passport'))
    address = models.CharField(max_length=255, verbose_name=_('Address'))
    map_link = models.URLField(blank=True, null=True, verbose_name=_('Map Link (is not required)'))

    date = models.DateField(verbose_name=_('Date'))
    start_time = models.TimeField(verbose_name=_('Start Time'))
    end_time = models.TimeField(verbose_name=_('End Time'))
    payment_amount = models.DecimalField(max_digits=8, decimal_places=2, verbose_name=_('Payment Amount'))
    date_choice = models.CharField(
        max_length=10, choices=DATE_CHOICES, default=DATE_TODAY, verbose_name=_('Date choices')
    )
    payment_unit = models.CharField(
        max_length=10, choices=PAYMENT_UNIT_CHOICES, default=PAYMENT_SHIFT, verbose_name=_('Payment Type')
    )
    payment_method = models.CharField(
        max_length=10, choices=PAYMENT_METHOD_CHOICES, default=PAYMENT_CASH, verbose_name=_('Payment method')
    )
    skills = models.TextField(verbose_name=_('Skills Description'))

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name=_('Status')
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    channel = models.ForeignKey(
        Channel,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    extra = models.JSONField(blank=True, default=dict)

    def __str__(self):
        return f'<{self.pk}>: {self.people_count}× ({self.get_status_display()})'

    def delete(self, **kwargs):
        from .services.observers.subscriber_setup import vacancy_publisher
        vacancy_publisher.notify(VACANCY_DELETE, data={'vacancy': self})
        super().delete(**kwargs)

    @property
    def members(self) -> QuerySet['VacancyUser']:
        return self.users.filter(status=Status.MEMBER)

    @property
    def last_channel_message(self) -> Optional[ChannelMessage]:
        return ChannelMessage.objects.filter(extra__vacancy_id=self.id).order_by('-created_at').first()

    class Meta:
        verbose_name = _('Vacancy')
        verbose_name_plural = _('Vacancies')

class VacancyUser(models.Model):
    user = models.ForeignKey('user.User', on_delete=models.CASCADE, verbose_name=_('User'))
    vacancy = models.ForeignKey('Vacancy', on_delete=models.CASCADE, related_name='users', verbose_name=_('Vacancy'))
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.MEMBER,
        verbose_name=_('Status')
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated at'))
    created_at = models.DateTimeField(default=timezone.now, blank=True, null=True, verbose_name=_('Created at'))

    class Meta:
        verbose_name = _('User in vacancy')
        verbose_name_plural = _('Users in vacancy')

class VacancyUserCall(models.Model):
    vacancy_user = models.ForeignKey(VacancyUser, on_delete=models.CASCADE, verbose_name=_('Vacancy user'))
    status = models.CharField(
        max_length=20,
        choices=CallStatus.choices,
        default=CallStatus.SENT,
        verbose_name=_('Call status')
    )
    call_type = models.CharField(
        max_length=20,
        choices=CallType.choices,
        verbose_name=_('Call type')
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Updated at'))
    created_at = models.DateTimeField(default=timezone.now, blank=True, null=True, verbose_name=_('Created at'))

    class Meta:
        verbose_name = _('User call in vacancy')
        verbose_name_plural = _('User calls in vacancy')


class VacancyStatusHistory(models.Model):
    vacancy = models.ForeignKey('Vacancy', on_delete=models.CASCADE, related_name='status_history', verbose_name=_('Vacancy'))
    new_status = models.CharField(max_length=20, choices=STATUS_CHOICES, verbose_name=_('New status'))
    changed_by = models.ForeignKey(get_user_model(), on_delete=models.SET_NULL, null=True, verbose_name=_('Changed by'))
    changed_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Changed at'))
    comment = models.TextField(null=True, blank=True, verbose_name=_('Comment'))

    def __str__(self):
        return f'{self.new_status} at {self.changed_at}'

    class Meta:
        verbose_name = _('Status history')
        verbose_name_plural = _('Status history')