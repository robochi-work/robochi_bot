"""Stage 3.D: admin callback handlers for a disputed 2nd rollcall.

Buttons:
- confirm        : finalize rollcall with current selected count
- edit           : (placeholder) open the vacancy detail page for the admin
- unblock_yes/no : after confirm with count=0, decide whether to unblock the
                    employer.

Race protection: if the employer self-completed the rollcall in the meantime,
admin_buttons_disabled flag is True; we answer with an alert and do nothing.
"""

from __future__ import annotations

import logging

import sentry_sdk
from django.conf import settings
from django.urls import reverse
from telebot.types import CallbackQuery

from telegram.handlers.bot_instance import bot
from telegram.handlers.common import CallbackStorage as Storage
from telegram.handlers.common import F
from vacancy.models import Vacancy
from vacancy.services.disputed_rollcall import (
    finalize_rollcall,
    get_disputed,
    is_disputed,
)

logger = logging.getLogger(__name__)


def _answer_alert(call: CallbackQuery, text: str) -> None:
    try:
        bot.answer_callback_query(call.id, text=text, show_alert=True)
    except Exception:
        sentry_sdk.capture_exception()


@bot.callback_query_handler(func=F(Storage.disputed_action.filter()))
def handle_disputed_action(call: CallbackQuery):
    try:
        data = Storage.disputed_action.parse(callback_data=call.data)
    except Exception:
        sentry_sdk.capture_exception()
        return

    action = data.get("action")
    try:
        vacancy = Vacancy.objects.get(pk=int(data["vacancy_id"]))
    except (Vacancy.DoesNotExist, KeyError, ValueError):
        _answer_alert(call, "Вакансія не знайдена.")
        return

    if not is_disputed(vacancy):
        _answer_alert(call, "Перекличка вже завершена.")
        return

    state = get_disputed(vacancy)
    if state.get("admin_buttons_disabled"):
        _answer_alert(call, "Заказчик вже пройшов перекличку самостійно.")
        return

    if action == "confirm":
        _handle_confirm(call, vacancy, state)
    elif action == "edit":
        _handle_edit(call, vacancy)
    elif action == "unblock_yes":
        _handle_unblock(call, vacancy, unblock=True)
    elif action == "unblock_no":
        _handle_unblock(call, vacancy, unblock=False)
    else:
        _answer_alert(call, "Невідома дія.")


def _handle_confirm(call: CallbackQuery, vacancy: Vacancy, state: dict) -> None:
    """Admin pressed "Підтвердити кількість"."""
    selected_ids = state.get("selected_ids") or []

    if not selected_ids:
        # Count = 0: ask admin whether to unblock the employer
        from vacancy.services.call_markup import get_admin_unblock_employer_modal_markup

        try:
            bot.send_message(
                chat_id=call.from_user.id,
                text=(f"Кількість підтверджених робочих по вакансії #{vacancy.id} — 0.\nРозблокувати замовника?"),
                reply_markup=get_admin_unblock_employer_modal_markup(vacancy),
            )
            bot.answer_callback_query(call.id)
        except Exception:
            sentry_sdk.capture_exception()
        return

    # Count > 0: finalize immediately
    try:
        confirmed = finalize_rollcall(vacancy, final_selected_user_ids=selected_ids, finalized_by="admin")
        _answer_alert(call, f"Готово. Підтверджено: {confirmed}. Рахунок надіслано.")
    except Exception:
        sentry_sdk.capture_exception()
        _answer_alert(call, "Помилка при завершенні переклички.")


def _handle_edit(call: CallbackQuery, vacancy: Vacancy) -> None:
    """Admin pressed "Редагувати кількість" — open vacancy detail (admin moderates).

    Full admin-moderation view is in Stage 4. For now, send a link.
    """
    try:
        url = settings.BASE_URL.rstrip("/") + reverse("vacancy:detail", args=[vacancy.id]) + "?focus=rollcall"
        bot.send_message(
            chat_id=call.from_user.id,
            text=f"Перейти до переклички: {url}",
        )
        bot.answer_callback_query(call.id)
    except Exception:
        sentry_sdk.capture_exception()


def _handle_unblock(call: CallbackQuery, vacancy: Vacancy, unblock: bool) -> None:
    """Finalize with count=0; optionally unblock the employer."""
    from user.services import BlockService

    try:
        finalize_rollcall(vacancy, final_selected_user_ids=[], finalized_by="admin")
        if unblock:
            try:
                BlockService.unblock_employer_rollcall_fail(user=vacancy.owner)
            except Exception:
                logger.exception("unblock employer failed")
            _answer_alert(call, "Перекличку завершено, замовника розблоковано.")
        else:
            _answer_alert(call, "Перекличку завершено, замовник лишається у блоці.")
    except Exception:
        sentry_sdk.capture_exception()
        _answer_alert(call, "Помилка при завершенні переклички.")
