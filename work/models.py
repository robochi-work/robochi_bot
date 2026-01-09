from django.db import models
from django.utils.translation import gettext_lazy as _
from .choices import WorkProfileRole


class UserWorkProfile(models.Model):
    user = models.OneToOneField('user.User', on_delete=models.CASCADE, related_name='work_profile', verbose_name=_("User"))
    city = models.ForeignKey('city.City', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("City"))
    role = models.CharField(max_length=20, choices=WorkProfileRole.choices, null=True, blank=True, verbose_name=_("Role"))
    phone_number = models.CharField(max_length=20, null=True, blank=True, verbose_name=_("Phone number"))

    is_completed = models.BooleanField(default=False, verbose_name=_("Is completed"))
    agreement_accepted = models.BooleanField(default=False, verbose_name=_("Agreement accepted"))
    agreement_accepted_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Agreement accepted at"))

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at")) 

    def __str__(self):
            return f"{self.user} — {self.get_role_display()}"

    class Meta:
        verbose_name = _('User work profile')
        verbose_name_plural = _('User work profiles')

class AgreementText(models.Model):
    ROLE_EMPLOYER = "employer"
    ROLE_WORKER = "worker"
    ROLE_CHOICES = [
        (ROLE_EMPLOYER, "Роботодавець"),
        (ROLE_WORKER, "Працівник"),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, unique=True)
    title = models.CharField(max_length=255, default="Договір о співпраці")
    text = models.TextField()

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Agreement ({self.role})"

from django.utils import timezone

agreement_accepted = models.BooleanField(default=False)
agreement_accepted_at = models.DateTimeField(null=True, blank=True)
