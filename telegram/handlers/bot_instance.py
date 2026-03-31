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
    try:
        from telegram.handlers.messages import commands  # noqa
        from telegram.handlers.contact import user_phone_number  # noqa
        from telegram.handlers.member.bot import channel as bot_channel  # noqa
        from telegram.handlers.member.bot import group as bot_group  # noqa
        from telegram.handlers.member.user import group as user_group  # noqa
        from telegram.handlers.callback import call  # noqa
        from telegram.handlers.callback import work_role  # noqa
        from telegram.handlers.messages import group as msg_group  # noqa
        from telegram.handlers.messages import worker_phone as worker_phone_handler  # noqa
        _handlers_loaded = True
        logger.info("load_handlers_once OK: all handlers registered")
    except Exception as e:
        logger.error(f"load_handlers_once FAILED: {e}", exc_info=True)
