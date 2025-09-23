from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class WorkConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'work'
    verbose_name = _("Work")
