"""Stage 6.B: callbacks for 'continue offer' DM buttons (Шукати ще / Залишити як є)."""

import json
import logging

from telebot.types import CallbackQuery

from telegram.handlers.bot_instance import bot
from vacancy.models import Vacancy
from vacancy.services.continue_offer import (
    is_within_continue_deadline,
    start_continue_search,
)

logger = logging.getLogger(__name__)


def _parse(callback: CallbackQuery, expected_t: str):
    try:
        data = json.loads(callback.data)
    except (json.JSONDecodeError, TypeError):
        return None, None
    if data.get("t") != expected_t:
        return None, None
    vacancy = Vacancy.objects.filter(id=data.get("v")).first()
    return data, vacancy


def _clear_offer_msg(vacancy: Vacancy, callback: CallbackQuery) -> None:
    try:
        bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
    except Exception:
        pass
    if vacancy.extra:
        vacancy.extra.pop("continue_offer_msg_id", None)
        vacancy.save(update_fields=["extra"])


@bot.callback_query_handler(func=lambda c: c.data and '"t": "co_search"' in c.data)
def handle_continue_offer_search(callback: CallbackQuery) -> None:
    _, vacancy = _parse(callback, "co_search")
    if not vacancy:
        bot.answer_callback_query(callback.id, "Вакансія не знайдена.")
        return

    if not is_within_continue_deadline(vacancy):
        _clear_offer_msg(vacancy, callback)
        bot.answer_callback_query(callback.id, "Вже пізно — час пошуку вичерпано.", show_alert=True)
        return

    _clear_offer_msg(vacancy, callback)
    try:
        start_continue_search(vacancy)
        bot.answer_callback_query(callback.id, "✅ Пошук розпочато")
    except Exception:
        logger.exception(f"start_continue_search failed for vacancy {vacancy.pk}")
        bot.answer_callback_query(callback.id, "Сталася помилка. Спробуйте пізніше.", show_alert=True)


@bot.callback_query_handler(func=lambda c: c.data and '"t": "co_ignore"' in c.data)
def handle_continue_offer_ignore(callback: CallbackQuery) -> None:
    _, vacancy = _parse(callback, "co_ignore")
    if not vacancy:
        return
    _clear_offer_msg(vacancy, callback)
    bot.answer_callback_query(callback.id, "Залишено як є")
