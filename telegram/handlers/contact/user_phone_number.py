import logging
from typing import Any
from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _
from telebot import types
from telebot.types import ReplyKeyboardRemove, WebAppInfo
from urllib.parse import urlencode

from telegram.handlers.bot_instance import bot
from telegram.handlers.utils import user_required
from user.models import User, AuthIdentity

logger = logging.getLogger(__name__)


@bot.message_handler(content_types=['contact'])
@user_required
def contact(message: types.Message, user: User, **kwargs: dict[str, Any]) -> None:
    logger.warning(f"CONTACT HANDLER CALLED: user_id={message.from_user.id}")
    try:
        if message.contact and message.contact.phone_number:
            phone = f"+{message.contact.phone_number.lstrip('+')}"
            user.phone_number = phone
            user.save(update_fields=['phone_number'])

            AuthIdentity.objects.get_or_create(
                provider=AuthIdentity.Provider.PHONE,
                provider_uid=phone,
                defaults={'user': user},
            )

            # Delete the contact message from chat
            bot.delete_message(
                chat_id=message.chat.id,
                message_id=message.message_id,
            )

            # Send welcome message (no inline button)
            bot.send_message(
                chat_id=message.chat.id,
                text='Вітаємо у нашому сервісі!',
                reply_markup=ReplyKeyboardRemove(),
            )
            logger.warning(f"CONTACT SAVED: phone={phone}")

            # Notify admins with complete user data (now includes phone)
            from telegram.utils import notify_admins_new_user
            notify_admins_new_user(user)

            # Set MenuButton "ПОЧАТИ" -> WebApp on wizard
            try:
                next_path = '/' if user.work_profile.is_completed else '/work/wizard/'
            except Exception:
                next_path = '/work/wizard/'

            check_url = reverse('telegram:telegram_check_web_app')
            webapp_url = settings.BASE_URL.rstrip('/') + check_url + '?' + urlencode({'next': next_path})

            bot.set_chat_menu_button(
                chat_id=message.chat.id,
                menu_button=types.MenuButtonWebApp(
                    type='web_app',
                    text='ПОЧАТИ',
                    web_app=WebAppInfo(url=webapp_url),
                ),
            )
            logger.warning(f"MENU BUTTON SET: chat_id={message.chat.id}, url={webapp_url}")

    except Exception as e:
        logger.error(f"CONTACT FAILED: {type(e).__name__}: {e}", exc_info=True)
