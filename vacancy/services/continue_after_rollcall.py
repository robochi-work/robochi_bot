"""Stage 6.A: helpers for the 1-hour continue-search window after 1st rollcall.

Flow:
- Employer presses "Підтвердити наявних + шукати ще" on 1st rollcall page.
- View vacancy_continue_search?confirm_rollcall=1 sets:
    extra["continue_after_first_rollcall"] = True
    extra["continue_started_at"] = ISO timestamp
    extra["continue_deadline"]    = ISO timestamp (started + 1h)
    first_rollcall_passed = True
  and schedules finalize_continue_after_rollcall_task with countdown=3600.

- Finalization happens via ONE of:
    a) Celery task fires after 1h (auto).
    b) Employer presses "Зупинити пошук" (immediate).
  In both cases:
    - 0 workers   → auto-close as "Закрити вакансію" (CLOSED + 3h timer).
    - ≥1 workers  → snapshot current members, stop search, scenario_b admin notify.

The function is IDEMPOTENT: if called twice, the second call is a noop.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from telegram.choices import CallStatus, CallType
from vacancy.choices import STATUS_CLOSED, STATUS_SEARCH_STOPPED
from vacancy.models import Vacancy, VacancyUserCall

logger = logging.getLogger(__name__)


def is_in_continue_mode(vacancy: Vacancy) -> bool:
    return bool((vacancy.extra or {}).get("continue_after_first_rollcall"))


def clear_continue_flags(vacancy: Vacancy) -> None:
    """Remove continue-mode flags from extra (caller saves)."""
    if not vacancy.extra:
        return
    for k in ("continue_after_first_rollcall", "continue_started_at", "continue_deadline"):
        vacancy.extra.pop(k, None)


def finalize_continue_after_first_rollcall(vacancy: Vacancy) -> dict:
    """Finalize the 1h continue-search window.

    Returns dict with "action": "finalized" | "auto_closed" | "noop".
    """
    if not is_in_continue_mode(vacancy):
        return {"action": "noop", "reason": "not in continue mode"}

    members = list(vacancy.members.select_related("user"))
    member_ids = [vu.user_id for vu in members]
    now = timezone.now()

    if not member_ids:
        # Empty group → auto-close
        vacancy.status = STATUS_CLOSED
        vacancy.closed_at = now
        vacancy.search_active = False
        if vacancy.extra is None:
            vacancy.extra = {}
        vacancy.extra["cancel_requested"] = True
        clear_continue_flags(vacancy)
        vacancy.save(update_fields=["status", "closed_at", "search_active", "extra"])

        _remove_channel_button(vacancy)
        _notify_admin_no_workers(vacancy)
        logger.info(f"finalize_continue_after_first_rollcall: vacancy {vacancy.pk} auto-closed (0 workers)")
        return {"action": "auto_closed", "vacancy_id": vacancy.pk}

    # ≥1 worker → snapshot + stop search
    from vacancy.services.call import create_vacancy_call
    from vacancy.services.rollcall_snapshot import save_first_rollcall_snapshot

    create_vacancy_call(vacancy=vacancy, call_type=CallType.START, status=CallStatus.CREATED)
    VacancyUserCall.objects.filter(
        vacancy_user__vacancy=vacancy,
        vacancy_user__user_id__in=member_ids,
        call_type=CallType.START,
    ).update(status=CallStatus.CONFIRM)

    if vacancy.extra is None:
        vacancy.extra = {}
    extra_calls = vacancy.extra.get("calls", {})
    extra_calls[CallType.START] = member_ids
    vacancy.extra["calls"] = extra_calls

    vacancy.status = STATUS_SEARCH_STOPPED
    vacancy.search_active = False
    vacancy.search_stopped_at = now
    clear_continue_flags(vacancy)
    vacancy.save(update_fields=["status", "search_active", "search_stopped_at", "extra"])

    # snapshot is the source of truth for 2nd rollcall — save_first_rollcall_snapshot
    # calls vacancy.save() itself, so it MUST come after our save above to avoid
    # update_fields overwriting its write.
    save_first_rollcall_snapshot(vacancy, member_ids)

    _remove_channel_button(vacancy)

    if len(member_ids) < vacancy.people_count:
        _notify_admin_scenario_b(vacancy, confirmed=len(member_ids))

    logger.info(
        f"finalize_continue_after_first_rollcall: vacancy {vacancy.pk} finalized "
        f"with {len(member_ids)} workers (plan: {vacancy.people_count})"
    )
    return {"action": "finalized", "vacancy_id": vacancy.pk, "members": len(member_ids)}


# ─── internal helpers ─────────────────────────────────────────────────────────


def _remove_channel_button(vacancy: Vacancy) -> None:
    """Update channel message to 'Пошук завершено' (no I-am-ready button)."""
    if not vacancy.channel:
        return
    try:
        from service.notifications import NotificationMethod
        from service.telegram_strategy_factory import TelegramStrategyFactory
        from telegram.handlers.bot_instance import bot
        from telegram.models import ChannelMessage
        from vacancy.services.vacancy_formatter import VacancyTelegramTextFormatter

        text = VacancyTelegramTextFormatter(vacancy).for_channel(status="full")
        channel_message = (
            ChannelMessage.objects.filter(channel_id=vacancy.channel.id, extra__vacancy_id=vacancy.id)
            .order_by("-id")
            .first()
        )
        if channel_message:
            strategy = TelegramStrategyFactory.get_strategy(NotificationMethod.TEXT)
            strategy.update(bot, vacancy.channel.id, text=text, message_id=channel_message.message_id)
    except Exception as e:
        logger.warning(f"Failed to update channel message for vacancy {vacancy.pk}: {e}")


def _notify_admin_scenario_b(vacancy: Vacancy, *, confirmed: int) -> None:
    try:
        from service.broadcast_service import TelegramBroadcastService
        from service.notifications_impl import TelegramNotifier
        from telegram.handlers.bot_instance import bot
        from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

        broadcast = TelegramBroadcastService(notifier=TelegramNotifier(bot))
        broadcast.admin_broadcast(
            text=CallVacancyTelegramTextFormatter(vacancy=vacancy).admin_scenario_b(
                confirmed=confirmed, needed=vacancy.people_count
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Failed to notify admins (scenario_b) for vacancy {vacancy.pk}: {e}")


def _notify_admin_no_workers(vacancy: Vacancy) -> None:
    try:
        from service.broadcast_service import TelegramBroadcastService
        from service.notifications_impl import TelegramNotifier
        from telegram.handlers.bot_instance import bot
        from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

        broadcast = TelegramBroadcastService(notifier=TelegramNotifier(bot))
        broadcast.admin_broadcast(
            text=CallVacancyTelegramTextFormatter(vacancy=vacancy).admin_employer_closed_no_workers(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Failed to notify admins (no_workers) for vacancy {vacancy.pk}: {e}")
