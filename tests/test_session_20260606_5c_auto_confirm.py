"""Tests for Stage 5.C: auto_confirm_ignored_rollcall_task."""

from __future__ import annotations

import datetime as _dt
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from telegram.choices import CallStatus, CallType, Status
from vacancy.choices import STATUS_AWAITING_PAYMENT, STATUS_SEARCH_STOPPED
from vacancy.models import VacancyUser, VacancyUserCall
from vacancy.services.disputed_rollcall import is_disputed, mark_disputed
from vacancy.services.rollcall_snapshot import save_first_rollcall_snapshot
from vacancy.tasks.call import auto_confirm_ignored_rollcall_task


def _vacancy_ignored(vacancy_factory, employer_factory, worker_factory, group_factory, *, hours_past_end, n=2):
    employer = employer_factory()
    group = group_factory()
    # Use local time so naive time() values match _get_end_aware semantics
    tz = timezone.get_current_timezone()
    now = timezone.now()
    end_dt_local = (now - _dt.timedelta(hours=hours_past_end)).astimezone(tz)
    start_dt_local = end_dt_local - _dt.timedelta(hours=8)
    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_SEARCH_STOPPED,
        first_rollcall_passed=True,
        group=group,
        date=start_dt_local.date(),
        start_time=start_dt_local.time().replace(microsecond=0),
        end_time=end_dt_local.time().replace(microsecond=0),
    )
    workers = []
    for _ in range(n):
        w = worker_factory()
        vu = VacancyUser.objects.create(vacancy=vacancy, user=w, status=Status.MEMBER)
        VacancyUserCall.objects.create(vacancy_user=vu, call_type=CallType.AFTER_START, status=CallStatus.CREATED)
        workers.append(w)
    save_first_rollcall_snapshot(vacancy, [w.id for w in workers])
    vacancy.refresh_from_db()
    return vacancy, employer, workers


@pytest.fixture(autouse=True)
def _stub_side_effects(monkeypatch):
    monkeypatch.setattr("vacancy.services.invoice.send_vacancy_invoice", lambda **kw: None)
    monkeypatch.setattr(
        "user.services.BlockService.auto_block_rollcall_reject",
        staticmethod(lambda *a, **kw: None),
    )
    monkeypatch.setattr(
        "user.services.BlockService.unblock_employer_rollcall_fail",
        staticmethod(lambda *a, **kw: None),
    )
    fake = MagicMock()
    monkeypatch.setattr("telegram.handlers.bot_instance.bot", fake, raising=False)


@pytest.mark.django_db
def test_auto_confirms_after_3h_ignore(vacancy_factory, employer_factory, worker_factory, group_factory):
    vacancy, _, _ = _vacancy_ignored(vacancy_factory, employer_factory, worker_factory, group_factory, hours_past_end=4)
    auto_confirm_ignored_rollcall_task()
    vacancy.refresh_from_db()
    assert vacancy.second_rollcall_passed is True
    assert vacancy.status == STATUS_AWAITING_PAYMENT
    assert vacancy.extra.get("auto_confirmed_at_ignore")


@pytest.mark.django_db
def test_does_not_confirm_before_3h(vacancy_factory, employer_factory, worker_factory, group_factory):
    vacancy, _, _ = _vacancy_ignored(vacancy_factory, employer_factory, worker_factory, group_factory, hours_past_end=1)
    auto_confirm_ignored_rollcall_task()
    vacancy.refresh_from_db()
    assert vacancy.second_rollcall_passed is False
    assert not vacancy.extra.get("auto_confirmed_at_ignore")


@pytest.mark.django_db
def test_skips_vacancy_with_disputed_state(vacancy_factory, employer_factory, worker_factory, group_factory):
    """If employer started a disputed rollcall, auto-confirm must NOT fire."""
    vacancy, _, workers = _vacancy_ignored(
        vacancy_factory, employer_factory, worker_factory, group_factory, hours_past_end=4
    )
    mark_disputed(
        vacancy,
        first_count=2,
        selected_user_ids=[workers[0].id],
        rejected_user_ids=[workers[1].id],
        is_full_uncheck=False,
    )
    auto_confirm_ignored_rollcall_task()
    vacancy.refresh_from_db()
    # Disputed state preserved; second_rollcall NOT marked
    assert is_disputed(vacancy)
    assert vacancy.second_rollcall_passed is False


@pytest.mark.django_db
def test_does_not_run_twice(vacancy_factory, employer_factory, worker_factory, group_factory):
    """Second invocation must not change anything."""
    vacancy, _, _ = _vacancy_ignored(vacancy_factory, employer_factory, worker_factory, group_factory, hours_past_end=4)
    auto_confirm_ignored_rollcall_task()
    vacancy.refresh_from_db()
    first_ts = vacancy.extra.get("auto_confirmed_at_ignore")

    auto_confirm_ignored_rollcall_task()
    vacancy.refresh_from_db()
    assert vacancy.extra.get("auto_confirmed_at_ignore") == first_ts


@pytest.mark.django_db
def test_skips_vacancy_without_snapshot(vacancy_factory, employer_factory, worker_factory, group_factory):
    """Vacancy with no snapshot (1st rollcall never passed) must be skipped."""
    employer = employer_factory()
    group = group_factory()
    tz = timezone.get_current_timezone()
    now = timezone.now()
    end_dt_local = (now - _dt.timedelta(hours=4)).astimezone(tz)
    start_dt_local = end_dt_local - _dt.timedelta(hours=8)
    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_SEARCH_STOPPED,
        first_rollcall_passed=False,
        group=group,
        date=start_dt_local.date(),
        start_time=start_dt_local.time().replace(microsecond=0),
        end_time=end_dt_local.time().replace(microsecond=0),
    )
    auto_confirm_ignored_rollcall_task()
    vacancy.refresh_from_db()
    assert vacancy.second_rollcall_passed is False
