"""Інлайн-колбеки для AdminHelpRequest."""

from __future__ import annotations

import logging

import sentry_sdk
from django.utils.translation import gettext as _
from telebot.types import CallbackQuery

from telegram.handlers.bot_instance import bot
from user.models import User
from user.services.admin_help import AdminHelpService

logger = logging.getLogger(__name__)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("adminhelp:cancel:"))
def cancel_help(call: CallbackQuery) -> None:
    try:
        req_id = int(call.data.split(":")[-1])
        user = User.objects.filter(id=call.from_user.id).first()
        if not user:
            bot.answer_callback_query(call.id)
            return
        AdminHelpService.cancel_request(user, req_id)
        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=_("❌ Скасовано."),
            )
        except Exception:
            pass
        bot.answer_callback_query(call.id, _("Скасовано"))
    except Exception:
        sentry_sdk.capture_exception()
        bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("adminhelp:close:"))
def close_help(call: CallbackQuery) -> None:
    try:
        req_id = int(call.data.split(":")[-1])
        admin_user = User.objects.filter(id=call.from_user.id).first()
        AdminHelpService.close_request(req_id, by_user=admin_user)
        bot.answer_callback_query(call.id, _("Закрито"))
    except Exception:
        sentry_sdk.capture_exception()
        bot.answer_callback_query(call.id)
