"""
Utility helpers for reminder message rotation.

Pattern: each reminder deletes the previous message and saves the new message_id.
This prevents stale buttons from being clicked after the reminder cycle ends.
"""

import logging

from telegram.handlers.bot_instance import get_bot

logger = logging.getLogger(__name__)


def delete_bot_message(chat_id: int, message_id: int | None) -> None:
    """Safely delete a bot message. Silently ignores errors."""
    if not message_id:
        return
    try:
        get_bot().delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.debug(f"delete_bot_message: chat={chat_id} msg={message_id}: {e}")


def send_and_track(
    chat_id: int,
    text: str,
    reply_markup=None,
    previous_message_id: int | None = None,
) -> int | None:
    """
    Delete previous message, send new one, return new message_id.
    Returns None if send fails.
    """
    delete_bot_message(chat_id, previous_message_id)
    try:
        msg = get_bot().send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
        )
        return msg.message_id
    except Exception as e:
        logger.warning(f"send_and_track: chat={chat_id}: {e}")
        return None
