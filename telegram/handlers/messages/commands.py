import base64
import json
import logging
from types import SimpleNamespace
from typing import Any

logger = logging.getLogger(__name__)

from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _
from telebot import types
from urllib.parse import urlencode

from telebot.types import Message, InlineKeyboardMarkup, CallbackQuery, ReplyKeyboardMarkup, InlineKeyboardButton, \
    WebAppInfo, MenuButtonWebApp

from service.notifications import NotificationMethod
from telegram.handlers.common import CallbackStorage as Storage
from telegram.handlers.bot_instance import bot, get_bot
from telegram.handlers.utils import user_required
from telegram.handlers.common import ButtonStorage, F, CallbackStorage
from vacancy.services.observers.subscriber_setup import telegram_notifier
from work.choices import WorkProfileRole
from user.models import User


@user_required
def choose_role(message: Message, **kwargs: dict[str, Any]) -> None:
    markup = InlineKeyboardMarkup()
    markup.add(ButtonStorage.work_role(label=str(WorkProfileRole.WORKER.label), role=WorkProfileRole.WORKER.value))
    markup.add(ButtonStorage.work_role(label=str(WorkProfileRole.EMPLOYER.label), role=WorkProfileRole.EMPLOYER.value))

    get_bot().send_message(
        message.chat.id,
        _('Welcome to robochi.work! Choose your role below.'),
        reply_markup=markup,
    )
@user_required
def fill_work_account(message: Message, **kwargs: dict[str, Any]) -> None:
    markup = InlineKeyboardMarkup()
    next_path = reverse('work:wizard')
    check_url = reverse('telegram:telegram_check_web_app')
    url = settings.BASE_URL.rstrip('/') + check_url + '?' + urlencode({'next': next_path})
    markup.add(ButtonStorage.web_app(label=_('Fill out the form'), url=url))
    get_bot().send_message(message.chat.id, text=_('You must fill out a work form'), reply_markup=markup)

@user_required
def ask_phone(message: Message, user: User, **kwargs):
    bot = get_bot()
    # Remove WebApp MenuButton so user sees ReplyKeyboard for phone
    try:
        bot.set_chat_menu_button(
            chat_id=message.chat.id,
            menu_button=types.MenuButtonDefault(type='default'),
        )
        bot.delete_my_commands(scope=types.BotCommandScopeChat(chat_id=message.chat.id))
    except Exception as e:
        logger.error(f"RESET_MENU_BUTTON FAILED: {e}")
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add(types.KeyboardButton(_('Надіслати номер телефону'), request_contact=True))
    logger.warning(f"ASK_PHONE CALLED: chat_id={message.chat.id}, user={user.pk}")
    try:
        bot.send_message(
            message.chat.id,
            _('Для продовження надішліть ваш номер телефону:'),
            reply_markup=markup,
            parse_mode=None,
        )
        logger.warning("ASK_PHONE SENT OK")
    except Exception as e:
        logger.error(f"ASK_PHONE FAILED: {e}")

@user_required
def default_start(message: Message, user: User, **kwargs):
    bot = get_bot()
    try:
        next_path = '/' if user.work_profile.is_completed else '/work/wizard/'
    except Exception:
        next_path = '/work/wizard/'
    check_url = reverse('telegram:telegram_check_web_app')
    url = settings.BASE_URL.rstrip('/') + check_url + '?' + urlencode({'next': next_path})

    # Set MenuButton "ПОЧАТИ" -> WebApp
    try:
        bot.set_chat_menu_button(
            chat_id=message.chat.id,
            menu_button=MenuButtonWebApp(
                type='web_app',
                text='ПОЧАТИ',
                web_app=types.WebAppInfo(url=url),
            ),
        )
    except Exception as e:
        logger.error(f"SET_MENU_BUTTON FAILED: {e}", exc_info=True)

    bot.send_message(
        message.chat.id,
        _('Вітаємо у нашому сервісі!\nНатискайте кнопку ПОЧАТИ нижче.'),
    )

def decode_start_param(encoded: str) -> dict:
    """Декодирование safe Base64 в словарь"""
    padding = "=" * (-len(encoded) % 4)  # Восстанавливаем "="
    decoded_str = base64.urlsafe_b64decode(encoded + padding).decode()
    return json.loads(decoded_str)

def process_start_payload(payload: str, message) -> bool:
    try:
        data = decode_start_param(payload)

        if data.get("type") == 'feedback':
            url = settings.BASE_URL.rstrip('/') + reverse('vacancy:feedback', kwargs={'pk': data.get("vacancy_id")})
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton(
                    text=_('Open'),
                    web_app=WebAppInfo(url=url)
                )
            )
            get_bot().send_message(
                message.chat.id,
                text=_('Send feedback'),
                reply_markup=markup
            )
            return True

        elif data.get("type") == 'info':
            send_info(message)
            return True
        else:
            return False

    except Exception as e:
        return False

@bot.message_handler(commands=['start'])
@bot.callback_query_handler(func=F(CallbackStorage.menu.filter(name='start')))
@user_required
def start(query: Message | CallbackQuery, user: User, **kwargs: dict[str, Any]) -> None:
    logger.warning(f"START CALLED: user={user.pk}, phone={user.phone_number}")
    if isinstance(query, CallbackQuery):
        message = query.message
    else:
        message = query

    if message.text:
        parts = message.text.split(maxsplit=1)
        if len(parts) > 1:
            result = process_start_payload(parts[1], message)
            if result:
                return

    try:
        if not user.phone_number:
            logger.warning(f"START → ask_phone")
            ask_phone(message, user=user)
        else:
            logger.warning(f"START → default_start")
            default_start(message, user=user)
    except Exception as e:
        logger.error(f"START FAILED: {type(e).__name__}: {e}", exc_info=True)


@bot.message_handler(commands=['info'])
@bot.callback_query_handler(func=F(Storage.menu.filter()))
def send_info(message):
    if isinstance(message, CallbackQuery):
        message = message.message

    files = ['telegram/media/Договір оферти.docx', 'telegram/media/Політика конфіденційності.docx', ]
    for file_path in files:
        try:
            with open(file_path, 'rb') as f:

                bot.send_document(
                    chat_id=message.chat.id,
                    document=f,
                )
        except Exception as e:
            ...
