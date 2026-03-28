from django.db import models
from django.utils.translation import gettext_lazy as _
from .choices import WorkProfileRole


class UserWorkProfile(models.Model):
    user = models.OneToOneField('user.User', on_delete=models.CASCADE, related_name='work_profile', verbose_name=_("User"))
    city = models.ForeignKey('city.City', on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("City"))
    role = models.CharField(max_length=20, choices=WorkProfileRole.choices, null=True, blank=True, verbose_name=_("Role"))
    phone_number = models.CharField(max_length=20, null=True, blank=True, verbose_name=_("Phone number"))
    is_completed = models.BooleanField(default=False, verbose_name=_("Is completed"))
    agreement_accepted = models.BooleanField(default=False)
    agreement_accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    # Multi-city feature for employers
    multi_city_enabled = models.BooleanField(
        default=False,
        verbose_name=_("Multi-city enabled"),
        help_text=_("Allow employer to post vacancies in multiple cities"),
    )
    allowed_cities = models.ManyToManyField(
        'city.City',
        blank=True,
        related_name='allowed_employers',
        verbose_name=_("Allowed cities"),
        help_text=_("Cities where employer can post vacancies (in addition to main city)"),
    )

    def __str__(self):
        return f"{self.user} — {self.get_role_display()}"

    class Meta:
        verbose_name = _('User work profile')
        verbose_name_plural = _('User work profiles')


class AgreementText(models.Model):
    TYPE_EMPLOYER = "employer"
    TYPE_WORKER = "worker"
    TYPE_OFFER = "offer"
    TYPE_CHOICES = [
        (TYPE_EMPLOYER, _("Agreement for Employer")),
        (TYPE_WORKER, _("Agreement for Worker")),
        (TYPE_OFFER, _("Public offer and Privacy policy")),
    ]

    role = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        unique=True,
        verbose_name=_("Type"),
    )
    title = models.CharField(max_length=255, default="Договір о співпраці", verbose_name=_("Title"))
    text = models.TextField(verbose_name=_("Text"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))

    def __str__(self):
        return f"{self.get_role_display()}"

    class Meta:
        verbose_name = _("Agreement text")
        verbose_name_plural = _("Agreement texts")
