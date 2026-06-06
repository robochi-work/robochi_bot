"""Tests for Stage 3.C: disputed_rollcall_reminders_task."""

from __future__ import annotations

import datetime as _dt
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from telegram.choices import Status
from vacancy.choices import STATUS_SEARCH_STOPPED
from vacancy.models import VacancyUser
from vacancy.services.disputed_rollcall import (
    DISPUTED_KEY,
    get_disputed,
    mark_disputed,
)
from vacancy.services.rollcall_snapshot import save_first_rollcall_snapshot
from vacancy.tasks.call import disputed_rollcall_reminders_task


def _make_disputed_vacancy(
    vacancy_factory, employer_factory, worker_factory, group_factory, is_full_uncheck=False, n=2
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
        VacancyUser.objects.create(vacancy=vacancy, user=w, status=Status.MEMBER)
        workers.append(w)
    save_first_rollcall_snapshot(vacancy, [w.id for w in workers])
    mark_disputed(
        vacancy,
        first_count=n,
        selected_user_ids=[workers[0].id] if n >= 1 else [],
        rejected_user_ids=[w.id for w in workers[1:]],
        is_full_uncheck=is_full_uncheck,
    )
    vacancy.refresh_from_db()
    return vacancy, employer, workers


@pytest.fixture(autouse=True)
def _stub_bot(monkeypatch):
    fake_bot = MagicMock()
    fake_bot.send_message = MagicMock(return_value=MagicMock(message_id=1))
    monkeypatch.setattr("telegram.handlers.bot_instance.bot", fake_bot, raising=False)
    return fake_bot


@pytest.mark.django_db
def test_first_reminder_sent_immediately_when_last_is_none(
    vacancy_factory, employer_factory, worker_factory, group_factory, _stub_bot
):
    """No prior reminder -> first message must be sent and count = 1."""
    vacancy, employer, workers = _make_disputed_vacancy(
        vacancy_factory, employer_factory, worker_factory, group_factory
    )
    assert get_disputed(vacancy)["reminders_count"] == 0

    disputed_rollcall_reminders_task()

    vacancy.refresh_from_db()
    state = get_disputed(vacancy)
    assert state["reminders_count"] == 1
    assert state["last_reminder_at"] is not None
    _stub_bot.send_message.assert_called_once()
    assert _stub_bot.send_message.call_args.kwargs["chat_id"] == employer.id


@pytest.mark.django_db
def test_no_reminder_within_5_minutes(vacancy_factory, employer_factory, worker_factory, group_factory, _stub_bot):
    """Last reminder 2 minutes ago -> no new send."""
    vacancy, _, _ = _make_disputed_vacancy(vacancy_factory, employer_factory, worker_factory, group_factory)
    state = get_disputed(vacancy)
    state["reminders_count"] = 1
    state["last_reminder_at"] = (timezone.now() - _dt.timedelta(minutes=2)).isoformat()
    vacancy.extra[DISPUTED_KEY] = state
    vacancy.save(update_fields=["extra"])

    disputed_rollcall_reminders_task()
    _stub_bot.send_message.assert_not_called()
    vacancy.refresh_from_db()
    assert get_disputed(vacancy)["reminders_count"] == 1


@pytest.mark.django_db
def test_reminder_sent_after_5_minutes(vacancy_factory, employer_factory, worker_factory, group_factory, _stub_bot):
    """Last reminder 6 minutes ago -> new send."""
    vacancy, _, _ = _make_disputed_vacancy(vacancy_factory, employer_factory, worker_factory, group_factory)
    state = get_disputed(vacancy)
    state["reminders_count"] = 1
    state["last_reminder_at"] = (timezone.now() - _dt.timedelta(minutes=6)).isoformat()
    vacancy.extra[DISPUTED_KEY] = state
    vacancy.save(update_fields=["extra"])

    disputed_rollcall_reminders_task()
    _stub_bot.send_message.assert_called_once()
    vacancy.refresh_from_db()
    assert get_disputed(vacancy)["reminders_count"] == 2


@pytest.mark.django_db
def test_stop_after_12_reminders(vacancy_factory, employer_factory, worker_factory, group_factory, _stub_bot):
    """12 reminders already sent -> no further sends."""
    vacancy, _, _ = _make_disputed_vacancy(vacancy_factory, employer_factory, worker_factory, group_factory)
    state = get_disputed(vacancy)
    state["reminders_count"] = 12
    state["last_reminder_at"] = (timezone.now() - _dt.timedelta(hours=1)).isoformat()
    vacancy.extra[DISPUTED_KEY] = state
    vacancy.save(update_fields=["extra"])

    disputed_rollcall_reminders_task()
    _stub_bot.send_message.assert_not_called()


@pytest.mark.django_db
def test_scenario_v_not_reminded(vacancy_factory, employer_factory, worker_factory, group_factory, _stub_bot):
    """Scenario В (full uncheck): employer is blocked, no reminders should be sent."""
    vacancy, _, _ = _make_disputed_vacancy(
        vacancy_factory,
        employer_factory,
        worker_factory,
        group_factory,
        is_full_uncheck=True,
    )
    disputed_rollcall_reminders_task()
    _stub_bot.send_message.assert_not_called()


@pytest.mark.django_db
def test_no_disputed_no_action(vacancy_factory, employer_factory, worker_factory, group_factory, _stub_bot):
    """Vacancy without disputed state must not trigger any reminder."""
    employer = employer_factory()
    group = group_factory()
    vacancy_factory(
        owner=employer,
        status=STATUS_SEARCH_STOPPED,
        first_rollcall_passed=True,
        group=group,
    )
    disputed_rollcall_reminders_task()
    _stub_bot.send_message.assert_not_called()
