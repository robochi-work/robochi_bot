"""Tests for Stage 3.D: admin callback handlers for disputed rollcall."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from telegram.choices import CallStatus, CallType, Status
from vacancy.choices import STATUS_SEARCH_STOPPED
from vacancy.models import VacancyUser, VacancyUserCall
from vacancy.services.disputed_rollcall import (
    DISPUTED_KEY,
    is_disputed,
    mark_disputed,
)
from vacancy.services.rollcall_snapshot import save_first_rollcall_snapshot


def _setup(
    vacancy_factory, employer_factory, worker_factory, group_factory, selected_count=1, n=2, is_full_uncheck=False
):
    employer = employer_factory()
    group = group_factory()
    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_SEARCH_STOPPED,
        first_rollcall_passed=True,
        group=group,
    )
    workers = []
    for _ in range(n):
        w = worker_factory()
        vu = VacancyUser.objects.create(vacancy=vacancy, user=w, status=Status.MEMBER)
        VacancyUserCall.objects.create(vacancy_user=vu, call_type=CallType.AFTER_START, status=CallStatus.CREATED)
        workers.append(w)
    save_first_rollcall_snapshot(vacancy, [w.id for w in workers])
    sel = [w.id for w in workers[:selected_count]]
    rej = [w.id for w in workers[selected_count:]]
    mark_disputed(
        vacancy,
        first_count=n,
        selected_user_ids=sel,
        rejected_user_ids=rej,
        is_full_uncheck=is_full_uncheck,
    )
    vacancy.refresh_from_db()
    return vacancy, employer, workers


def _call(action: str, vacancy_id: int) -> MagicMock:
    from telegram.handlers.common import CallbackStorage as Storage

    call = MagicMock()
    call.id = "cbq-1"
    call.from_user.id = 99999
    call.data = Storage.disputed_action.new(action=action, vacancy_id=vacancy_id)
    return call


@pytest.fixture(autouse=True)
def _stub_bot(monkeypatch):
    fake = MagicMock()
    fake.answer_callback_query = MagicMock()
    fake.send_message = MagicMock()
    monkeypatch.setattr("telegram.handlers.callback.disputed_rollcall.bot", fake)
    return fake


@pytest.fixture(autouse=True)
def _stub_finalize_side_effects(monkeypatch):
    """Stub invoice/ban/unblock so tests stay isolated."""
    monkeypatch.setattr("vacancy.services.invoice.send_vacancy_invoice", lambda **kw: None)
    monkeypatch.setattr(
        "user.services.BlockService.auto_block_rollcall_reject",
        staticmethod(lambda *a, **kw: None),
    )
    monkeypatch.setattr(
        "user.services.BlockService.unblock_employer_rollcall_fail",
        staticmethod(lambda *a, **kw: None),
    )


@pytest.mark.django_db
def test_confirm_with_count_gt_zero_finalizes(
    vacancy_factory, employer_factory, worker_factory, group_factory, _stub_bot
):
    vacancy, _, _ = _setup(
        vacancy_factory,
        employer_factory,
        worker_factory,
        group_factory,
        selected_count=1,
        n=2,
    )
    from telegram.handlers.callback.disputed_rollcall import handle_disputed_action

    handle_disputed_action(_call("confirm", vacancy.id))

    vacancy.refresh_from_db()
    assert vacancy.second_rollcall_passed is True
    assert not is_disputed(vacancy)
    _stub_bot.answer_callback_query.assert_called()


@pytest.mark.django_db
def test_confirm_with_count_zero_opens_unblock_modal(
    vacancy_factory, employer_factory, worker_factory, group_factory, _stub_bot
):
    vacancy, _, _ = _setup(
        vacancy_factory,
        employer_factory,
        worker_factory,
        group_factory,
        selected_count=0,
        n=2,
        is_full_uncheck=True,
    )
    from telegram.handlers.callback.disputed_rollcall import handle_disputed_action

    handle_disputed_action(_call("confirm", vacancy.id))

    # Modal sent, rollcall NOT yet finalized
    _stub_bot.send_message.assert_called_once()
    text = _stub_bot.send_message.call_args.kwargs.get("text", "")
    assert "Розблокувати замовника" in text
    vacancy.refresh_from_db()
    assert is_disputed(vacancy)
    assert vacancy.second_rollcall_passed is False


@pytest.mark.django_db
def test_unblock_yes_finalizes_and_unblocks(
    vacancy_factory, employer_factory, worker_factory, group_factory, _stub_bot, monkeypatch
):
    vacancy, employer, _ = _setup(
        vacancy_factory,
        employer_factory,
        worker_factory,
        group_factory,
        selected_count=0,
        n=2,
        is_full_uncheck=True,
    )
    calls = {"unblock": 0}
    monkeypatch.setattr(
        "user.services.BlockService.unblock_employer_rollcall_fail",
        staticmethod(lambda **kw: calls.__setitem__("unblock", calls["unblock"] + 1)),
    )

    from telegram.handlers.callback.disputed_rollcall import handle_disputed_action

    handle_disputed_action(_call("unblock_yes", vacancy.id))

    vacancy.refresh_from_db()
    assert vacancy.second_rollcall_passed is True
    assert not is_disputed(vacancy)
    # unblock was called inside finalize_rollcall AND inside _handle_unblock
    assert calls["unblock"] >= 1


@pytest.mark.django_db
def test_unblock_no_finalizes_without_unblock(
    vacancy_factory, employer_factory, worker_factory, group_factory, _stub_bot
):
    vacancy, _, _ = _setup(
        vacancy_factory,
        employer_factory,
        worker_factory,
        group_factory,
        selected_count=0,
        n=2,
        is_full_uncheck=True,
    )
    from telegram.handlers.callback.disputed_rollcall import handle_disputed_action

    handle_disputed_action(_call("unblock_no", vacancy.id))

    vacancy.refresh_from_db()
    assert vacancy.second_rollcall_passed is True
    assert not is_disputed(vacancy)


@pytest.mark.django_db
def test_buttons_disabled_alerts_admin(vacancy_factory, employer_factory, worker_factory, group_factory, _stub_bot):
    vacancy, _, _ = _setup(
        vacancy_factory,
        employer_factory,
        worker_factory,
        group_factory,
        selected_count=1,
        n=2,
    )
    state = vacancy.extra[DISPUTED_KEY]
    state["admin_buttons_disabled"] = True
    vacancy.extra[DISPUTED_KEY] = state
    vacancy.save(update_fields=["extra"])

    from telegram.handlers.callback.disputed_rollcall import handle_disputed_action

    handle_disputed_action(_call("confirm", vacancy.id))

    vacancy.refresh_from_db()
    # Still disputed; admin got an alert
    assert is_disputed(vacancy)
    _stub_bot.answer_callback_query.assert_called()
    kwargs = _stub_bot.answer_callback_query.call_args.kwargs
    assert kwargs.get("show_alert") is True


@pytest.mark.django_db
def test_edit_sends_link(vacancy_factory, employer_factory, worker_factory, group_factory, _stub_bot):
    vacancy, _, _ = _setup(
        vacancy_factory,
        employer_factory,
        worker_factory,
        group_factory,
        selected_count=1,
        n=2,
    )
    from telegram.handlers.callback.disputed_rollcall import handle_disputed_action

    handle_disputed_action(_call("edit", vacancy.id))

    _stub_bot.send_message.assert_called_once()
    text = _stub_bot.send_message.call_args.kwargs.get("text", "")
    assert "Перейти" in text or "focus=rollcall" in text
