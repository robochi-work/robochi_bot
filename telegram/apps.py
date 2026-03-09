from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class TelegramConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'telegram'
    verbose_name = _("Telegram")

    def ready(self):
        from telegram.handlers.bot_instance import load_handlers_once
        load_handlers_once()
