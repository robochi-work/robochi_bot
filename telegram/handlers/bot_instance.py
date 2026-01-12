import logging
import telebot
from django.conf import settings

logger = logging.getLogger(__name__)

bot = telebot.TeleBot(settings.TELEGRAM_BOT_TOKEN, parse_mode="HTML")

_handlers_loaded = False

def load_handlers_once():
    global _handlers_loaded
    if _handlers_loaded:
        return
    _handlers_loaded = True

    # импортируй тут модули с хендлерами я¬Ќќ, без walk_packages
    # (это убирает непредсказуемые циклы)
    from telegram.handlers.messages import commands  # noqa
    from telegram.handlers.messages import info  # noqa
    # добавь остальные handler-модули аналогично
