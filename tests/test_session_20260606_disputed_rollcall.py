"""Tests for the disputed_rollcall service (Stage 3.A)."""

from __future__ import annotations

import pytest

from telegram.choices import CallStatus, CallType, Status
from vacancy.choices import STATUS_AWAITING_PAYMENT, STATUS_SEARCH_STOPPED
from vacancy.models import VacancyUser, VacancyUserCall
from vacancy.services.disputed_rollcall import (
    DISPUTED_KEY,
    clear_disputed,
    disable_admin_buttons,
    finalize_rollcall,
    get_disputed,
    increment_reminders,
    is_disputed,
    mark_disputed,
)
from vacancy.services.rollcall_snapshot import save_first_rollcall_snapshot


def _setup_vacancy_with_workers(vacancy_factory, worker_factory, n_workers=2):
    """Helper: vacancy in SEARCH_STOPPED with n MEMBER VacancyUsers + AFTER_START rollcall records."""
    vacancy = vacancy_factory(status=STATUS_SEARCH_STOPPED, first_rollcall_passed=True)
    workers = [worker_factory() for _ in range(n_workers)]
    for w in workers:
        vu = VacancyUser.objects.create(vacancy=vacancy, user=w, status=Status.MEMBER)
        VacancyUserCall.objects.create(vacancy_user=vu, call_type=CallType.AFTER_START, status=CallStatus.CREATED)
    save_first_rollcall_snapshot(vacancy, [w.id for w in workers])
    vacancy.refresh_from_db()
    return vacancy, workers


@pytest.mark.django_db
def test_mark_and_get_disputed(vacancy_factory, worker_factory):
    vacancy, workers = _setup_vacancy_with_workers(vacancy_factory, worker_factory, 3)
    state = mark_disputed(
        vacancy,
        first_count=3,
        selected_user_ids=[workers[0].id],
        rejected_user_ids=[workers[1].id, workers[2].id],
        is_full_uncheck=False,
    )
    assert is_disputed(vacancy)
    assert state["first_count"] == 3
    assert state["second_count"] == 1
    assert state["is_full_uncheck"] is False
    assert sorted(state["rejected_ids"]) == sorted([workers[1].id, workers[2].id])
    assert state["reminders_count"] == 0
    assert state["admin_buttons_disabled"] is False


@pytest.mark.django_db
def test_mark_full_uncheck(vacancy_factory, worker_factory):
    vacancy, workers = _setup_vacancy_with_workers(vacancy_factory, worker_factory, 2)
    mark_disputed(
        vacancy,
        first_count=2,
        selected_user_ids=[],
        rejected_user_ids=[w.id for w in workers],
        is_full_uncheck=True,
    )
    state = get_disputed(vacancy)
    assert state["is_full_uncheck"] is True
    assert state["second_count"] == 0


@pytest.mark.django_db
def test_increment_reminders(vacancy_factory, worker_factory):
    vacancy, workers = _setup_vacancy_with_workers(vacancy_factory, worker_factory, 2)
    mark_disputed(
        vacancy,
        first_count=2,
        selected_user_ids=[workers[0].id],
        rejected_user_ids=[workers[1].id],
        is_full_uncheck=False,
    )
    assert increment_reminders(vacancy) == 1
    assert increment_reminders(vacancy) == 2
    vacancy.refresh_from_db()
    assert get_disputed(vacancy)["reminders_count"] == 2


@pytest.mark.django_db
def test_disable_admin_buttons(vacancy_factory, worker_factory):
    vacancy, workers = _setup_vacancy_with_workers(vacancy_factory, worker_factory, 2)
    mark_disputed(
        vacancy,
        first_count=2,
        selected_user_ids=[workers[0].id],
        rejected_user_ids=[workers[1].id],
        is_full_uncheck=False,
    )
    disable_admin_buttons(vacancy)
    assert get_disputed(vacancy)["admin_buttons_disabled"] is True


@pytest.mark.django_db
def test_clear_disputed(vacancy_factory, worker_factory):
    vacancy, workers = _setup_vacancy_with_workers(vacancy_factory, worker_factory, 2)
    mark_disputed(
        vacancy,
        first_count=2,
        selected_user_ids=[workers[0].id],
        rejected_user_ids=[workers[1].id],
        is_full_uncheck=False,
    )
    clear_disputed(vacancy)
    vacancy.refresh_from_db()
    assert not is_disputed(vacancy)
    assert DISPUTED_KEY not in vacancy.extra


@pytest.mark.django_db
def test_finalize_rollcall_confirms_and_rejects(vacancy_factory, worker_factory, monkeypatch):
    """All-positive scenario: finalize with 1 confirmed of 2."""
    vacancy, workers = _setup_vacancy_with_workers(vacancy_factory, worker_factory, 2)
    mark_disputed(
        vacancy,
        first_count=2,
        selected_user_ids=[workers[0].id],
        rejected_user_ids=[workers[1].id],
        is_full_uncheck=False,
    )

    # Stub external side-effects (invoice, ban, unblock) to keep test isolated
    called = {"invoice": 0, "ban": 0, "unblock": 0}

    def _stub_invoice(*args, **kwargs):
        called["invoice"] += 1

    def _stub_ban(*args, **kwargs):
        called["ban"] += 1
        from user.models import UserBlock

        return UserBlock(pk=0)

    def _stub_unblock(*args, **kwargs):
        called["unblock"] += 1

    # Patch the real module path because finalize_rollcall does a local import
    monkeypatch.setattr("vacancy.services.invoice.send_vacancy_invoice", _stub_invoice)
    monkeypatch.setattr("user.services.BlockService.auto_block_rollcall_reject", staticmethod(_stub_ban))
    monkeypatch.setattr("user.services.BlockService.unblock_employer_rollcall_fail", staticmethod(_stub_unblock))

    confirmed = finalize_rollcall(vacancy, final_selected_user_ids=[workers[0].id], finalized_by="employer")
    assert confirmed == 1

    # Workers got correct call statuses
    vu0 = VacancyUser.objects.get(vacancy=vacancy, user=workers[0])
    vu1 = VacancyUser.objects.get(vacancy=vacancy, user=workers[1])
    call0 = VacancyUserCall.objects.get(vacancy_user=vu0, call_type=CallType.AFTER_START)
    call1 = VacancyUserCall.objects.get(vacancy_user=vu1, call_type=CallType.AFTER_START)
    assert call0.status == CallStatus.CONFIRM
    assert call1.status == CallStatus.REJECT

    # Side-effects called
    assert called["ban"] == 1  # only worker[1] banned
    assert called["unblock"] == 1
    assert called["invoice"] == 1

    # Vacancy state
    vacancy.refresh_from_db()
    assert vacancy.second_rollcall_passed is True
    assert vacancy.status == STATUS_AWAITING_PAYMENT
    assert not is_disputed(vacancy)
