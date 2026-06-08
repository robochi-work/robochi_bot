"""Tests for Stage 5.F: legacy 2nd-rollcall auto-confirm in _escalate_rollcall removed."""

from __future__ import annotations

import datetime as _dt
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from telegram.choices import Status
from vacancy.choices import STATUS_SEARCH_STOPPED
from vacancy.models import VacancyUser
from vacancy.services.rollcall_snapshot import save_first_rollcall_snapshot
from vacancy.tasks.call import _escalate_rollcall


@pytest.fixture(autouse=True)
def _stub_telegram(monkeypatch):
    fake = MagicMock()
    fake.send_message = MagicMock()
    monkeypatch.setattr("telegram.handlers.bot_instance.bot", fake, raising=False)
    monkeypatch.setattr("telegram.service.group.GroupService.kick_user", staticmethod(lambda **kw: None))
    monkeypatch.setattr(
        "service.broadcast_service.TelegramBroadcastService.admin_broadcast",
        lambda *a, **kw: None,
    )


@pytest.mark.django_db
def test_escalate_for_2nd_rollcall_does_not_auto_confirm(
    vacancy_factory, employer_factory, worker_factory, group_factory
):
    """5.F: escalation of 2nd rollcall must NOT mark second_rollcall_passed."""
    employer = employer_factory()
    group = group_factory()
    tz = timezone.get_current_timezone()
    now = timezone.now()
    end_dt = (now - _dt.timedelta(hours=1)).astimezone(tz)
    start_dt = end_dt - _dt.timedelta(hours=8)
    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_SEARCH_STOPPED,
        first_rollcall_passed=True,
        second_rollcall_passed=False,
        group=group,
        date=start_dt.date(),
        start_time=start_dt.time().replace(microsecond=0),
        end_time=end_dt.time().replace(microsecond=0),
    )
    workers = []
    for _ in range(2):
        w = worker_factory()
        VacancyUser.objects.create(vacancy=vacancy, user=w, status=Status.MEMBER)
        workers.append(w)
    save_first_rollcall_snapshot(vacancy, [w.id for w in workers])

    _escalate_rollcall(vacancy, call_label="2 переклички")
    vacancy.refresh_from_db()
    # 5.F: must NOT auto-confirm
    assert vacancy.second_rollcall_passed is False


@pytest.mark.django_db
def test_escalate_for_1st_rollcall_still_auto_confirms(
    vacancy_factory, employer_factory, worker_factory, group_factory
):
    """1st rollcall auto-confirm in _escalate_rollcall must still work (untouched by 5.F)."""
    employer = employer_factory()
    group = group_factory()
    tz = timezone.get_current_timezone()
    now = timezone.now()
    end_dt = (now + _dt.timedelta(hours=4)).astimezone(tz)
    start_dt = (now - _dt.timedelta(hours=1)).astimezone(tz)
    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_SEARCH_STOPPED,
        first_rollcall_passed=False,
        second_rollcall_passed=False,
        group=group,
        date=start_dt.date(),
        start_time=start_dt.time().replace(microsecond=0),
        end_time=end_dt.time().replace(microsecond=0),
    )
    for _ in range(2):
        w = worker_factory()
        VacancyUser.objects.create(vacancy=vacancy, user=w, status=Status.MEMBER)

    _escalate_rollcall(vacancy, call_label="1 переклички")
    vacancy.refresh_from_db()
    assert vacancy.first_rollcall_passed is True
