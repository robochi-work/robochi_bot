"""Disputed rollcall state and finalization.

Used when the 2nd rollcall (AFTER_START) ends with mismatched checkboxes
- Scenario B: employer unchecked some workers but at least 1 confirmed.
- Scenario C: employer unchecked ALL workers (also kicked + blocked).

State is stored in vacancy.extra["disputed_rollcall"] until either:
- the employer re-submits the rollcall with a valid result, OR
- the admin presses "Підтвердити кількість" / "Редагувати кількість".

On finalize_rollcall(): rejected workers are banned, the invoice is sent,
the employer is unblocked, and the disputed-state is cleared.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from vacancy.models import Vacancy

logger = logging.getLogger(__name__)

DISPUTED_KEY = "disputed_rollcall"


def is_disputed(vacancy: Vacancy) -> bool:
    return bool(vacancy.extra.get(DISPUTED_KEY))


def get_disputed(vacancy: Vacancy) -> dict:
    return dict(vacancy.extra.get(DISPUTED_KEY) or {})


def mark_disputed(
    vacancy: Vacancy,
    *,
    first_count: int,
    selected_user_ids: Iterable[int],
    rejected_user_ids: Iterable[int],
    is_full_uncheck: bool,
) -> dict:
    """Persist the disputed-rollcall state on the vacancy."""
    state = {
        "first_count": int(first_count),
        "second_count": len(list(selected_user_ids)),
        "selected_ids": list({int(x) for x in selected_user_ids}),
        "rejected_ids": list({int(x) for x in rejected_user_ids}),
        "is_full_uncheck": bool(is_full_uncheck),
        "reminders_count": 0,
        "last_reminder_at": None,
        "admin_buttons_disabled": False,
    }
    vacancy.extra[DISPUTED_KEY] = state
    vacancy.save(update_fields=["extra"])
    logger.info(
        "disputed_rollcall_marked",
        extra={"vacancy_id": vacancy.pk, "is_full_uncheck": is_full_uncheck},
    )
    return state


def disable_admin_buttons(vacancy: Vacancy) -> None:
    """Race protection: employer self-completed before admin pressed a button."""
    state = get_disputed(vacancy)
    if not state:
        return
    state["admin_buttons_disabled"] = True
    vacancy.extra[DISPUTED_KEY] = state
    vacancy.save(update_fields=["extra"])


def increment_reminders(vacancy: Vacancy) -> int:
    from django.utils import timezone

    state = get_disputed(vacancy)
    if not state:
        return 0
    state["reminders_count"] = int(state.get("reminders_count", 0)) + 1
    state["last_reminder_at"] = timezone.now().isoformat()
    vacancy.extra[DISPUTED_KEY] = state
    vacancy.save(update_fields=["extra"])
    return state["reminders_count"]


def clear_disputed(vacancy: Vacancy) -> None:
    if DISPUTED_KEY in vacancy.extra:
        vacancy.extra.pop(DISPUTED_KEY, None)
        vacancy.save(update_fields=["extra"])


def finalize_rollcall(
    vacancy: Vacancy,
    *,
    final_selected_user_ids: Iterable[int],
    finalized_by: str = "employer",
) -> int:
    """Close the 2nd rollcall.

    - Marks confirmed VacancyUserCall as CONFIRM, the rest as REJECT
    - Bans workers who ended up rejected (only at this final stage)
    - Sets second_rollcall_passed=True, status=STATUS_AWAITING_PAYMENT
    - Sends invoice, unblocks employer
    - Clears disputed state

    Returns the number of confirmed workers.
    """
    from telegram.choices import CallStatus, CallType
    from user.services import BlockService
    from vacancy.choices import STATUS_AWAITING_PAYMENT
    from vacancy.models import VacancyUserCall
    from vacancy.services.invoice import send_vacancy_invoice
    from vacancy.services.rollcall_snapshot import get_snapshot_vacancy_users

    final_ids = {int(x) for x in final_selected_user_ids}
    rollcall_qs = get_snapshot_vacancy_users(vacancy)

    confirm_qs = rollcall_qs.filter(user_id__in=final_ids)
    reject_qs = rollcall_qs.exclude(user_id__in=final_ids)

    VacancyUserCall.objects.filter(vacancy_user__in=confirm_qs, call_type=CallType.AFTER_START).update(
        status=CallStatus.CONFIRM
    )
    VacancyUserCall.objects.filter(vacancy_user__in=reject_qs, call_type=CallType.AFTER_START).update(
        status=CallStatus.REJECT
    )

    # Ban rejected workers ONLY at finalization (no premature bans during the dispute)
    for vu in reject_qs.select_related("user"):
        try:
            BlockService.auto_block_rollcall_reject(user=vu.user, blocked_by=vacancy.owner)
        except Exception:
            logger.exception("finalize_rollcall: ban failed for user_id=%s", vu.user_id)

    # Update vacancy state
    vacancy.second_rollcall_passed = True
    vacancy.status = STATUS_AWAITING_PAYMENT
    vacancy.search_active = False
    vacancy.extra["calls"] = vacancy.extra.get("calls") or {}
    vacancy.extra["calls"][CallType.AFTER_START] = list(final_ids)
    vacancy.save(update_fields=["second_rollcall_passed", "status", "search_active", "extra"])

    # Unblock the employer (if blocked for rollcall fail)
    try:
        BlockService.unblock_employer_rollcall_fail(user=vacancy.owner)
    except Exception:
        logger.exception("finalize_rollcall: unblock employer failed")

    # Send invoice
    try:
        from service.notifications_impl import TelegramNotifier
        from telegram.handlers.bot_instance import bot as _bot

        send_vacancy_invoice(notifier=TelegramNotifier(_bot), vacancy=vacancy)
    except Exception:
        logger.exception("finalize_rollcall: invoice send failed")

    clear_disputed(vacancy)

    logger.info(
        "rollcall_finalized",
        extra={
            "vacancy_id": vacancy.pk,
            "confirmed": confirm_qs.count(),
            "rejected": reject_qs.count(),
            "by": finalized_by,
        },
    )
    return confirm_qs.count()
