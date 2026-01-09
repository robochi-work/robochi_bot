import base64
import json
from types import SimpleNamespace
from typing import Any

from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _
from telebot import types

from telebot.types import Message, InlineKeyboardMarkup, CallbackQuery, ReplyKeyboardMarkup, InlineKeyboardButton, \
    WebAppInfo

from service.notifications import NotificationMethod
from telegram.handlers.common import CallbackStorage as Storage
from telegram.handlers.bot_instance import bot
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

    bot.send_message(
        message.chat.id,
        'Вас вітає сервіс\nrobochi.work\nОбираите\nЯ ЗАМОВНИК\nта знаходьте будь яку кількість\nпрацівників швидко та зручно!\nАбо обираите\nЯ ПРАЦІВНИК\nта знаходьте підробіток\nколи зручно!\n',
        reply_markup=markup,
    )
@user_required
def fill_work_account(message: Message, **kwargs: dict[str, Any]) -> None:
    markup = InlineKeyboardMarkup()
    markup.add(ButtonStorage.web_app(label=_('Fill out the form'), url=settings.BASE_URL.rstrip('/') + reverse('work:wizard')))
    bot.send_message(message.chat.id, text=_('You must fill out a work form'), reply_markup=markup)

@user_required
def ask_phone(message: Message, user: User):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add(types.KeyboardButton(_('Send phone number'), request_contact=True))

    telegram_notifier.notify(
        recipient=SimpleNamespace(chat_id=message.chat.id, ),
        method=NotificationMethod.TEXT,
        text=_('It is necessary to send your phone number, use the button below'),
        reply_markup=markup,
    )

@user_required
def default_start(message: Message | None, user: User, **kwargs: dict[str, Any]) -> None:
    markup = InlineKeyboardMarkup()
    markup.add(ButtonStorage.web_app())
    markup.add(ButtonStorage.menu(menu_name='info', label=_('Info')))

    if user.is_staff:
        markup.add(
            ButtonStorage.web_app(
                label=_('Admin panel'), url=settings.BASE_URL.rstrip('/') + reverse('admin:index')
            )
        )

    text = _('Hello')

    message_common_settings = {
        'chat_id': user.id,
        'reply_markup': markup,
        'parse_mode': 'HTML',
    }

    bot.send_message(
        text=text,
        **message_common_settings,
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
            bot.send_message(
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

    if not user.phone_number:
        ask_phone(message, user=user)
    elif not user.work_profile.is_completed:
        fill_work_account(message, user=user)
    else:
        default_start(message, user=user)


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
