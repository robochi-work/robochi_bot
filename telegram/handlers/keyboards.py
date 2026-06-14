"""Reply-клавиатуры для бота."""

from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _
from telebot import types

BTN_OFFER_KEY = "📄 Public offer agreement"
BTN_ADMIN_HELP_KEY = "🆘 Help Administrator"
BTN_SEND_PHONE_KEY = "Надіслати номер телефону"


def _offer_webapp_url() -> str:
    """Сторінка оферти публічна — auth-обгортку через check-web-app не використовуємо,
    бо у WebApp з reply-кнопки initData недоступний (передається лише через sendData)."""
    base = settings.BASE_URL.rstrip("/")
    return f"{base}{reverse('work:legal_offer')}"


def main_persistent_keyboard() -> types.ReplyKeyboardMarkup:
    """2 постійні кнопки: оферта (WebApp) + допомога. Для зареєстрованих юзерів."""
    kb = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
    )
    kb.row(types.KeyboardButton(_(BTN_OFFER_KEY), web_app=types.WebAppInfo(url=_offer_webapp_url())))
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
    kb.row(types.KeyboardButton(_(BTN_OFFER_KEY), web_app=types.WebAppInfo(url=_offer_webapp_url())))
    kb.row(types.KeyboardButton(_(BTN_ADMIN_HELP_KEY)))
    return kb
