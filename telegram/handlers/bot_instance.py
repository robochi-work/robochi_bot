import logging
import telebot
from django.conf import settings

logger = logging.getLogger(__name__)

bot = telebot.TeleBot(settings.TELEGRAM_BOT_TOKEN, parse_mode="HTML")


def get_bot():
    return bot


_handlers_loaded = False

def load_handlers_once():
    global _handlers_loaded
    if _handlers_loaded:
        return
    _handlers_loaded = True

    from telegram.handlers.messages import commands  # noqa
    from telegram.handlers.contact import user_phone_number  # noqa
