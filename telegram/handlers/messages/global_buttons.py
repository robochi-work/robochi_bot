"""Глобальний хендлер для двох reply-кнопок та help-флоу."""

from __future__ import annotations

import logging

import sentry_sdk
from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import override
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from telegram.handlers.bot_instance import bot
from telegram.handlers.keyboards import (
    BTN_ADMIN_HELP_KEY,
    BTN_OFFER_KEY,
)
from user.models import User
from user.services.admin_help import AdminHelpService

logger = logging.getLogger(__name__)


def _collect_all_translations(key: str) -> set[str]:
    result = {key.lower()}
    for lang_code, _name in settings.LANGUAGES:
        try:
            with override(lang_code):
                result.add(_(key).lower())
        except Exception:
            pass
    return result


_OFFER_LABELS = _collect_all_translations(BTN_OFFER_KEY)
_ADMIN_HELP_LABELS = _collect_all_translations(BTN_ADMIN_HELP_KEY)


def _strip_emoji_prefix(text: str) -> str:
    parts = text.strip().split(maxsplit=1)
    return parts[-1].lower() if parts else ""


def _matches(text: str, labels: set[str]) -> bool:
    if not text:
        return False
    lower = text.lower()
    stripped = _strip_emoji_prefix(text)
    for label in labels:
        if label == lower or label == stripped:
            return True
        label_words = label.split(maxsplit=1)[-1]
        if label_words and label_words in lower:
            return True
    return False


def is_offer_click(text: str) -> bool:
    return _matches(text, _OFFER_LABELS)


def is_admin_help_click(text: str) -> bool:
    return _matches(text, _ADMIN_HELP_LABELS)


def _send_offer_link(chat_id: int) -> None:
    legal_path = reverse("work:legal_offer")
    check_url = reverse("telegram:telegram_check_web_app")
    base = settings.BASE_URL.rstrip("/")
    url = f"{base}{check_url}?next={legal_path}"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(_("📄 Open agreement"), url=url))
    bot.send_message(
        chat_id,
        _("Public offer agreement and Privacy policy:"),
        reply_markup=markup,
    )


def _is_relevant(m: Message) -> bool:
    if m.chat.type != "private":
        return False
    if m.from_user is None:
        return False
    text = m.text or m.caption or ""
    if is_offer_click(text) or is_admin_help_click(text):
        return True
    try:
        return AdminHelpService.is_pending_by_id(m.from_user.id)
    except Exception:
        return False


@bot.message_handler(
    func=_is_relevant,
    content_types=["text", "photo", "video", "voice", "video_note"],
)
def global_private_handler(message: Message) -> None:
    try:
        user = User.objects.filter(id=message.from_user.id).first()
        if not user:
            return
        text = message.text or message.caption or ""
        if is_offer_click(text):
            _send_offer_link(message.chat.id)
            return
        if is_admin_help_click(text):
            AdminHelpService.start_request(user)
            return
        if AdminHelpService.is_pending(user):
            AdminHelpService.submit_request(user, message)
            return
    except Exception:
        sentry_sdk.capture_exception()
        logger.exception("global_private_handler failed")
