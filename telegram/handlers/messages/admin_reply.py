"""Реплай адміна у службовій групі → пересилка юзеру."""

from __future__ import annotations

import logging

import sentry_sdk
from django.conf import settings
from telebot.types import Message

from telegram.handlers.bot_instance import bot
from user.models import AdminHelpRequest

logger = logging.getLogger(__name__)


def _admin_chat_id() -> int | None:
    val = getattr(settings, "ADMIN_HELP_CHAT_ID", None)
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _is_admin_reply(m: Message) -> bool:
    chat_id = _admin_chat_id()
    if chat_id is None:
        return False
    if m.chat.id != chat_id:
        return False
    if m.reply_to_message is None:
        return False
    return True


@bot.message_handler(
    func=_is_admin_reply,
    content_types=["text", "photo", "video", "voice", "video_note", "document"],
)
def admin_reply_to_user(message: Message) -> None:
    try:
        req = AdminHelpRequest.objects.filter(admin_chat_message_id=message.reply_to_message.message_id).first()
        if not req:
            return
        user_id = req.user_id
        admin_name = message.from_user.first_name or message.from_user.username or "Адміністратор"
        prefix = f"↪️ <b>{admin_name}</b> (адміністратор):\n\n"
        ct = message.content_type
        try:
            if ct == "text":
                bot.send_message(user_id, prefix + (message.text or ""), parse_mode="HTML")
            elif ct == "photo":
                bot.send_photo(
                    user_id, message.photo[-1].file_id, caption=prefix + (message.caption or ""), parse_mode="HTML"
                )
            elif ct == "video":
                bot.send_video(
                    user_id, message.video.file_id, caption=prefix + (message.caption or ""), parse_mode="HTML"
                )
            elif ct == "voice":
                bot.send_voice(user_id, message.voice.file_id, caption=prefix.strip())
            elif ct == "video_note":
                bot.send_message(user_id, prefix.strip(), parse_mode="HTML")
                bot.send_video_note(user_id, message.video_note.file_id)
            elif ct == "document":
                bot.send_document(
                    user_id, message.document.file_id, caption=prefix + (message.caption or ""), parse_mode="HTML"
                )
        except Exception as e:
            logger.warning(f"admin_reply: forward to user {user_id} failed: {e}")
            return
        try:
            from telebot import types as tg_types

            bot.set_message_reaction(
                chat_id=message.chat.id,
                message_id=message.message_id,
                reaction=[tg_types.ReactionTypeEmoji(emoji="✅")],
            )
        except Exception:
            pass
    except Exception:
        sentry_sdk.capture_exception()
        logger.exception("admin_reply_to_user failed")
