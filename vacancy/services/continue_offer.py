"""Stage 6.B: DM offer to employer 'продовжити пошук' after partial 1st rollcall.

Sent when:
- Employer pressed "Підтвердити" (not "Підтвердити + шукати ще")
- AND len(selected_users) >= 1 AND < people_count
- AND now < shift_start + 1h

Auto-deleted at shift_start + 1h via delete_continue_offer_task.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime as _dt
from datetime import timedelta as _td

from django.utils import timezone

from vacancy.models import Vacancy

logger = logging.getLogger(__name__)


def _shift_start_aware(vacancy: Vacancy):
    tz = timezone.get_current_timezone()
    return timezone.make_aware(_dt.combine(vacancy.date, vacancy.start_time), tz)


def send_continue_offer_dm(vacancy: Vacancy) -> None:
    """Send DM to employer with 'Шукати ще / Залишити як є' buttons."""
    try:
        from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

        from telegram.handlers.bot_instance import bot

        confirmed = (vacancy.extra or {}).get("calls", {}).get("start", [])
        confirmed_count = len(confirmed)
        needed = vacancy.people_count
        start_time_str = vacancy.start_time.strftime("%H:%M") if vacancy.start_time else "—"

        text = (
            f"⚠️ Підтверджено {confirmed_count} з {needed} робітників.\n"
            f"Початок роботи о {start_time_str}.\n\n"
            f"Шукати ще людей?"
        )

        kb = InlineKeyboardMarkup()
        kb.row(
            InlineKeyboardButton("🔍 Шукати ще", callback_data=json.dumps({"t": "co_search", "v": vacancy.id})),
        )
        kb.row(
            InlineKeyboardButton("✅ Залишити як є", callback_data=json.dumps({"t": "co_ignore", "v": vacancy.id})),
        )

        sent = bot.send_message(chat_id=vacancy.owner.id, text=text, reply_markup=kb)

        if sent and hasattr(sent, "message_id"):
            if vacancy.extra is None:
                vacancy.extra = {}
            vacancy.extra["continue_offer_msg_id"] = sent.message_id
            vacancy.save(update_fields=["extra"])
            _schedule_delete(vacancy)
    except Exception:
        logger.exception(f"send_continue_offer_dm failed for vacancy {vacancy.pk}")


def _schedule_delete(vacancy: Vacancy) -> None:
    try:
        from vacancy.tasks.call import delete_continue_offer_task

        deadline = _shift_start_aware(vacancy) + _td(hours=1)
        countdown = max(0, int((deadline - timezone.now()).total_seconds()))
        delete_continue_offer_task.apply_async(args=[vacancy.pk], countdown=countdown)
    except Exception:
        logger.exception(f"_schedule_delete failed for vacancy {vacancy.pk}")


def delete_continue_offer_msg(vacancy: Vacancy) -> None:
    """Delete the continue-offer DM if it still exists. Idempotent."""
    if not vacancy.extra:
        return
    msg_id = vacancy.extra.get("continue_offer_msg_id")
    if not msg_id:
        return
    try:
        from telegram.handlers.bot_instance import bot

        bot.delete_message(chat_id=vacancy.owner.id, message_id=msg_id)
    except Exception:
        pass
    vacancy.extra.pop("continue_offer_msg_id", None)
    vacancy.save(update_fields=["extra"])


def is_within_continue_deadline(vacancy: Vacancy) -> bool:
    """True if now < shift_start + 1h."""
    return timezone.now() < _shift_start_aware(vacancy) + _td(hours=1)


def start_continue_search(vacancy: Vacancy) -> None:
    """Reusable core of '_continue_search_after_first_rollcall' (no request).

    Used by view (form submit with search_more=1) and callback handler (DM button).
    """
    from vacancy.choices import STATUS_APPROVED
    from vacancy.services.observers.events import VACANCY_APPROVED as _VACANCY_APPROVED
    from vacancy.services.observers.subscriber_setup import vacancy_publisher as _vp
    from vacancy.tasks.call import finalize_continue_after_rollcall_task

    now = timezone.localtime(timezone.now())
    tz = timezone.get_current_timezone()

    new_start_dt = now + _td(hours=1)
    minute = (new_start_dt.minute // 15 + 1) * 15
    if minute >= 60:
        new_start_dt = (new_start_dt + _td(hours=1)).replace(minute=0, second=0, microsecond=0)
    else:
        new_start_dt = new_start_dt.replace(minute=minute, second=0, microsecond=0)
    vacancy.start_time = new_start_dt.time()
    vacancy.date = now.date()

    start_aware = timezone.make_aware(_dt.combine(vacancy.date, vacancy.start_time), tz)
    end_aware = timezone.make_aware(_dt.combine(vacancy.date, vacancy.end_time), tz)
    if vacancy.end_time < vacancy.start_time:
        end_aware += _td(days=1)
    if end_aware - start_aware < _td(hours=3):
        new_end = start_aware + _td(hours=3)
        vacancy.end_time = timezone.localtime(new_end).time()

    vacancy.first_rollcall_passed = True
    vacancy.status = STATUS_APPROVED
    vacancy.search_active = True
    vacancy.search_stopped_at = None

    extra = vacancy.extra or {}
    extra["continue_after_first_rollcall"] = True
    extra["continue_started_at"] = now.isoformat()
    extra["continue_deadline"] = (now + _td(hours=1)).isoformat()
    vacancy.extra = extra

    vacancy.save(
        update_fields=[
            "start_time",
            "end_time",
            "date",
            "first_rollcall_passed",
            "status",
            "search_active",
            "search_stopped_at",
            "extra",
        ]
    )

    _vp.notify(_VACANCY_APPROVED, data={"vacancy": vacancy})
    finalize_continue_after_rollcall_task.apply_async(args=[vacancy.pk], countdown=3600)
