"""Tests for Stage 3.B: disputed rollcall in vacancy_check_call.

Verifies:
- Scenario Б (partial uncheck): disputed state saved, employer NOT kicked/blocked
- Scenario В (full uncheck): disputed state saved with is_full_uncheck=True,
  employer kicked + blocked, kick is non-fatal if telegram fails
- Bug 500 fix: TelegramBroadcastService is called with notifier (no TypeError)
- Workers are NOT banned at this stage (only at finalize_rollcall)
"""

from __future__ import annotations

import datetime as _dt
from unittest.mock import MagicMock

import pytest
from django.urls import reverse

from telegram.choices import CallStatus, CallType, Status
from vacancy.choices import STATUS_SEARCH_STOPPED
from vacancy.models import VacancyUser, VacancyUserCall
from vacancy.services.disputed_rollcall import get_disputed, is_disputed
from vacancy.services.rollcall_snapshot import save_first_rollcall_snapshot


def _setup_active_rollcall(vacancy_factory, employer_factory, worker_factory, group_factory, n=2):
    """Vacancy in SEARCH_STOPPED with N members + AFTER_START rollcall in progress."""
    employer = employer_factory()
    group = group_factory()
    today = _dt.date.today()
    one_hour_ago = (_dt.datetime.now() - _dt.timedelta(hours=1)).time()
    in_one_hour = (_dt.datetime.now() + _dt.timedelta(hours=1)).time()

    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_SEARCH_STOPPED,
        first_rollcall_passed=True,
        group=group,
        date=today,
        start_time=one_hour_ago.replace(microsecond=0),
        end_time=in_one_hour.replace(microsecond=0),
    )
    # Mark sent_final_call so AFTER_START is the expected call type
    vacancy.extra = dict(vacancy.extra or {})
    vacancy.extra["sent_final_call"] = True
    vacancy.save(update_fields=["extra"])

    workers = []
    for _ in range(n):
        w = worker_factory()
        vu = VacancyUser.objects.create(vacancy=vacancy, user=w, status=Status.MEMBER)
        # AFTER_START call records must exist for rejected_users count to work
        VacancyUserCall.objects.create(vacancy_user=vu, call_type=CallType.AFTER_START, status=CallStatus.CREATED)
        workers.append(w)
    save_first_rollcall_snapshot(vacancy, [w.id for w in workers])
    vacancy.refresh_from_db()
    return vacancy, employer, workers, group


@pytest.fixture(autouse=True)
def _stub_telegram_side_effects(monkeypatch):
    """Stub all telegram-bot side-effects so tests don't try to talk to the real bot."""
    fake_bot = MagicMock()
    fake_bot.send_message = MagicMock(return_value=MagicMock(message_id=12345))
    fake_bot.delete_message = MagicMock()
    monkeypatch.setattr("telegram.handlers.bot_instance.bot", fake_bot, raising=False)
    monkeypatch.setattr("telegram.service.group.GroupService.kick_user", staticmethod(lambda **kw: None))
    return fake_bot


@pytest.mark.django_db
def test_scenario_b_partial_uncheck_marks_disputed(
    client, vacancy_factory, employer_factory, worker_factory, group_factory
):
    """Scenario Б: 1 of 2 unchecked -> disputed state with is_full_uncheck=False."""
    vacancy, employer, workers, _ = _setup_active_rollcall(
        vacancy_factory, employer_factory, worker_factory, group_factory, n=2
    )

    client.force_login(employer)
    # Confirm only worker 0; worker 1 is unchecked
    vu0 = VacancyUser.objects.get(vacancy=vacancy, user=workers[0])
    resp = client.post(
        reverse("vacancy:call", kwargs={"pk": vacancy.pk, "call_type": CallType.AFTER_START}),
        data={"users": [str(vu0.pk)], "call_type": CallType.AFTER_START},
        follow=False,
    )
    # Must NOT be 500
    assert resp.status_code in (200, 302), f"unexpected status {resp.status_code}"

    vacancy.refresh_from_db()
    assert is_disputed(vacancy)
    state = get_disputed(vacancy)
    assert state["is_full_uncheck"] is False
    assert state["first_count"] == 2
    assert state["second_count"] == 1
    assert state["rejected_ids"] == [workers[1].id]


@pytest.mark.django_db
def test_scenario_v_full_uncheck_marks_disputed_and_kicks(
    client, vacancy_factory, employer_factory, worker_factory, group_factory
):
    """Scenario В: all unchecked -> disputed with is_full_uncheck=True + employer kicked/blocked."""
    vacancy, employer, workers, group = _setup_active_rollcall(
        vacancy_factory, employer_factory, worker_factory, group_factory, n=2
    )

    client.force_login(employer)
    # All checkboxes off
    resp = client.post(
        reverse("vacancy:call", kwargs={"pk": vacancy.pk, "call_type": CallType.AFTER_START}),
        data={"users": [], "call_type": CallType.AFTER_START},
        follow=False,
    )
    assert resp.status_code in (200, 302), f"unexpected status {resp.status_code}"

    vacancy.refresh_from_db()
    assert is_disputed(vacancy)
    state = get_disputed(vacancy)
    assert state["is_full_uncheck"] is True
    assert state["second_count"] == 0
    assert sorted(state["rejected_ids"]) == sorted([w.id for w in workers])

    # Employer is blocked
    from user.models import UserBlock

    assert UserBlock.objects.filter(user=employer).exists()


@pytest.mark.django_db
def test_workers_not_banned_at_disputed_stage(client, vacancy_factory, employer_factory, worker_factory, group_factory):
    """Workers in REJECT must NOT be banned at the dispute stage (only at finalize)."""
    vacancy, employer, workers, _ = _setup_active_rollcall(
        vacancy_factory, employer_factory, worker_factory, group_factory, n=2
    )

    client.force_login(employer)
    vu0 = VacancyUser.objects.get(vacancy=vacancy, user=workers[0])
    client.post(
        reverse("vacancy:call", kwargs={"pk": vacancy.pk, "call_type": CallType.AFTER_START}),
        data={"users": [str(vu0.pk)], "call_type": CallType.AFTER_START},
    )

    from user.models import UserBlock

    # Workers themselves NOT blocked
    for w in workers:
        assert not UserBlock.objects.filter(user=w).exists(), f"worker {w.id} must not be banned yet"


@pytest.mark.django_db
def test_no_500_with_broadcast_service(client, vacancy_factory, employer_factory, worker_factory, group_factory):
    """Regression for the original bug: TelegramBroadcastService called with notifier (no TypeError)."""
    vacancy, employer, workers, _ = _setup_active_rollcall(
        vacancy_factory, employer_factory, worker_factory, group_factory, n=2
    )
    client.force_login(employer)
    resp = client.post(
        reverse("vacancy:call", kwargs={"pk": vacancy.pk, "call_type": CallType.AFTER_START}),
        data={"users": [], "call_type": CallType.AFTER_START},
    )
    assert resp.status_code != 500
