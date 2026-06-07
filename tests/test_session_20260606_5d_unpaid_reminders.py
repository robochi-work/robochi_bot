"""Tests for Stage 5.D: send_unpaid_reminders_task."""

from __future__ import annotations

import datetime as _dt
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from vacancy.choices import STATUS_AWAITING_PAYMENT
from vacancy.tasks.call import send_unpaid_reminders_task


@pytest.fixture(autouse=True)
def _stub_bot(monkeypatch):
    fake = MagicMock()
    fake.send_message = MagicMock(return_value=MagicMock(message_id=1))
    monkeypatch.setattr("telegram.handlers.bot_instance.bot", fake, raising=False)
    return fake


@pytest.mark.django_db
def test_first_reminder_sent(vacancy_factory, employer_factory, group_factory, _stub_bot):
    employer = employer_factory()
    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_AWAITING_PAYMENT,
        group=group_factory(),
    )
    send_unpaid_reminders_task()
    vacancy.refresh_from_db()
    assert vacancy.extra.get("unpaid_reminders") == 1
    assert vacancy.extra.get("unpaid_last_reminder_at") is not None
    _stub_bot.send_message.assert_called_once()


@pytest.mark.django_db
def test_no_reminder_within_one_hour(vacancy_factory, employer_factory, group_factory, _stub_bot):
    employer = employer_factory()
    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_AWAITING_PAYMENT,
        group=group_factory(),
        extra={
            "unpaid_reminders": 3,
            "unpaid_last_reminder_at": (timezone.now() - _dt.timedelta(minutes=10)).isoformat(),
        },
    )
    send_unpaid_reminders_task()
    vacancy.refresh_from_db()
    assert vacancy.extra.get("unpaid_reminders") == 3
    _stub_bot.send_message.assert_not_called()


@pytest.mark.django_db
def test_reminder_after_one_hour(vacancy_factory, employer_factory, group_factory, _stub_bot):
    employer = employer_factory()
    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_AWAITING_PAYMENT,
        group=group_factory(),
        extra={
            "unpaid_reminders": 5,
            "unpaid_last_reminder_at": (timezone.now() - _dt.timedelta(hours=1, minutes=1)).isoformat(),
        },
    )
    send_unpaid_reminders_task()
    vacancy.refresh_from_db()
    assert vacancy.extra.get("unpaid_reminders") == 6
    _stub_bot.send_message.assert_called_once()


@pytest.mark.django_db
def test_stops_sending_regular_reminders_after_24(vacancy_factory, employer_factory, group_factory, _stub_bot):
    """Once permanent_ban_done is set, no further messages are sent."""
    employer = employer_factory()
    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_AWAITING_PAYMENT,
        group=group_factory(),
        extra={
            "unpaid_reminders": 24,
            "unpaid_last_reminder_at": (timezone.now() - _dt.timedelta(hours=5)).isoformat(),
            "permanent_ban_done": True,
        },
    )
    send_unpaid_reminders_task()
    vacancy.refresh_from_db()
    assert vacancy.extra.get("unpaid_reminders") == 24
    _stub_bot.send_message.assert_not_called()


@pytest.mark.django_db
def test_skips_paid_vacancy(vacancy_factory, employer_factory, group_factory, _stub_bot):
    employer = employer_factory()
    vacancy_factory(
        owner=employer,
        status=STATUS_AWAITING_PAYMENT,
        group=group_factory(),
        extra={"is_paid": True},
    )
    send_unpaid_reminders_task()
    _stub_bot.send_message.assert_not_called()
