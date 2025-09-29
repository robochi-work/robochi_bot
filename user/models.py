from typing import Any, cast
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models

from user.choices import USER_GENDER_CHOICES
from work.models import UserWorkProfile


class CustomUserManager(UserManager):
    def create_user(self, **extra_fields: Any):
        user = self.model(**extra_fields)
        user.set_password(extra_fields.get('password'))
        user.save()
        return user

    def create_superuser(self, **extra_fields: Any):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(**extra_fields)

class User(AbstractUser):
    username = models.CharField(max_length=150, blank=True, null=True, unique=False, verbose_name=_('Username'))
    first_name = None
    last_name = None
    full_name = models.CharField(_('Full name'), max_length=150, blank=True, null=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True, verbose_name=_('Phone number'))
    birth_year = models.IntegerField(
        _('Birth year'),
        null=True,
        blank=True,
    )
    language_code = models.CharField(
        max_length=10,
        choices=settings.LANGUAGES,
        default=settings.LANGUAGE_CODE,
        verbose_name=_('Language'),
    )
    gender = models.CharField(choices=USER_GENDER_CHOICES, blank=True, null=True, verbose_name=_('Gender'))
    USERNAME_FIELD = 'id'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()
    class Meta:
        db_table = 'user'
        verbose_name = _('User')
        verbose_name_plural = _('Users')

    def __str__(self) -> str:
        return f'User: {self.pk} {self.username}'


class UserFeedback(models.Model):
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='feedbacks_given',
        verbose_name=_('Feedback author'),
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='feedbacks_received',
        verbose_name=_('Feedback recipient'),
    )
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created at'))

    extra = models.JSONField(blank=True, default=dict)

    class Meta:
        verbose_name = _('User feedback')
        verbose_name_plural = _('User feedbacks')


class UserWorkProfileInUser(UserWorkProfile):
    class Meta:
        proxy = True
        verbose_name = _('User work profile')
        verbose_name_plural = _('User work profiles')

