from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import reverse

from telegram.handlers.bot_instance import bot



class Command(BaseCommand):
    help = 'Installs Webhook for Telegram bot'

    def handle(self, *args: tuple[Any, ...], **kwargs: dict[str, Any]) -> None:
        bot.remove_webhook()
        url = settings.BASE_URL + reverse('telegram:telegram_webhook')
        print(url)
        print(bot.set_webhook(url=url, allowed_updates=settings.TELEGRAM_BOT_ALLOWED_UPDATES))
