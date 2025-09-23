import os
from threading import Thread

import telebot
from django.conf import settings

bot = telebot.TeleBot(settings.TELEGRAM_BOT_TOKEN, parse_mode='HTML')

if os.getenv('run_bot') == '1':
    os.environ['run_bot'] = '0'

    if bot.webhook_listener:
        bot.remove_webhook()
    Thread(target=lambda: bot.infinity_polling(
        allowed_updates=settings.TELEGRAM_BOT_ALLOWED_UPDATES
    )).start()