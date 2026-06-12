"""Reply-клавиатуры для бота."""

from django.utils.translation import gettext as _
from telebot import types

BTN_OFFER_KEY = "📄 Public offer agreement"
BTN_ADMIN_HELP_KEY = "🆘 Help Administrator"
BTN_SEND_PHONE_KEY = "Надіслати номер телефону"


def main_persistent_keyboard() -> types.ReplyKeyboardMarkup:
    """2 постійні кнопки. Для зареєстрованих юзерів."""
    kb = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
    )
    kb.row(types.KeyboardButton(_(BTN_OFFER_KEY)))
    kb.row(types.KeyboardButton(_(BTN_ADMIN_HELP_KEY)))
    return kb


def registration_keyboard() -> types.ReplyKeyboardMarkup:
    """3 кнопки на етапі запиту телефону."""
    kb = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
    )
    kb.row(types.KeyboardButton(_(BTN_SEND_PHONE_KEY), request_contact=True))
    kb.row(types.KeyboardButton(_(BTN_OFFER_KEY)))
    kb.row(types.KeyboardButton(_(BTN_ADMIN_HELP_KEY)))
    return kb
