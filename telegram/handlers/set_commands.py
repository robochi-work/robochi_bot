from telebot import types

from telegram.handlers.bot_instance import bot

commands_ru = [
    types.BotCommand(command="start", description="Запустить бота"),
    types.BotCommand(command="info", description="Информация о боте")
]
# bot.set_my_commands(commands=commands_ru, language_code='ru')

commands_uk = [
    types.BotCommand(command="start", description="Запустити бота"),
    types.BotCommand(command="info", description="Інформація про бота")
]
# bot.set_my_commands(commands=commands_uk, language_code='uk')