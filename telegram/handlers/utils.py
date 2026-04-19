from collections.abc import Callable
from functools import wraps
from typing import Any

import sentry_sdk
from django.core.exceptions import ObjectDoesNotExist
from django.utils import translation
from django.utils.translation import gettext as _
from telebot.types import CallbackQuery, Message, PreCheckoutQuery

from telegram.utils import get_or_create_user
from user.models import User
from work.service.work_profile import WorkProfileService


def _notify_banned(query, text: str) -> None:
    from telegram.handlers.bot_instance import bot

    if isinstance(query, Message):
        bot.send_message(query.chat.id, text)
    elif isinstance(query, CallbackQuery):
        bot.answer_callback_query(query.id, text, show_alert=True)
        if query.message:
            bot.send_message(query.message.chat.id, text)
    elif isinstance(query, PreCheckoutQuery):
        bot.answer_pre_checkout_query(query.id, ok=False, error_message=text)
    else:
        try:
            chat_id = getattr(getattr(query, "message", None), "chat", None).id or query.chat.id
            bot.send_message(chat_id, text)
        except Exception:
            sentry_sdk.capture_exception()


def user_required(func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    def wrapper(query: Message | CallbackQuery | PreCheckoutQuery, *args: Any, **kwargs: Any) -> Any:
        user = kwargs.get("user")

        if not isinstance(user, User):
            user_kwargs = {
                "first_name": getattr(query.from_user, "first_name", ""),
                "last_name": getattr(query.from_user, "last_name", ""),
                "username": query.from_user.username,
            }

            user, created = get_or_create_user(user_id=query.from_user.id, **user_kwargs)

            try:
                _profile = user.work_profile
                create_work_profile = _profile is None
            except ObjectDoesNotExist:
                create_work_profile = True

            if create_work_profile or created:
                WorkProfileService(user=user).get_profile()

            kwargs["user_created"] = created
            kwargs["user"] = user

        with translation.override(user.language_code):
            if not user.is_active:
                banned_text = _("Access Denied. Your account has been blocked.")
                _notify_banned(query, banned_text)
                return
            return func(query, *args, **kwargs)

    return wrapper
