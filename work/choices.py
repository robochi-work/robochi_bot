from django.db import models
from django.utils.translation import gettext_lazy as _


class WorkProfileRole(models.TextChoices):
    EMPLOYER = 'employer', _('Employer')
    WORKER = 'worker', _('Worker')