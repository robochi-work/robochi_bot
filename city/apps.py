from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CityConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'city'
    verbose_name = _("City")
