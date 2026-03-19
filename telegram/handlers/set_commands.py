from telebot import types
from telegram.handlers.bot_instance import get_bot


def setup_bot_commands():
    """Call once at startup or via management command."""
    bot = get_bot()

    commands_uk = [
        types.BotCommand(command="start", description="Запустити бота"),
        types.BotCommand(command="info", description="Інформація про бота"),
    ]
    bot.set_my_commands(commands=commands_uk, language_code='uk')

    commands_ru = [
        types.BotCommand(command="start", description="Запустить бота"),
        types.BotCommand(command="info", description="Информация о боте"),
    ]
    bot.set_my_commands(commands=commands_ru, language_code='ru')

    # Fallback (для всех остальных языков) — украинский
    bot.set_my_commands(commands=commands_uk)

    print("Bot commands set for uk, ru, and default")
