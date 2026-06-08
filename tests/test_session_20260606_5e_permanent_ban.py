"""Tests for Stage 5.E: permanent ban after 24 unpaid reminders."""

from __future__ import annotations

import datetime as _dt
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from user.choices import BlockReason, BlockType
from user.models import UserBlock
from vacancy.choices import STATUS_AWAITING_PAYMENT
from vacancy.tasks.call import send_unpaid_reminders_task


@pytest.fixture(autouse=True)
def _stub_bot(monkeypatch):
    fake = MagicMock()
    fake.send_message = MagicMock(return_value=MagicMock(message_id=1))
    monkeypatch.setattr("telegram.handlers.bot_instance.bot", fake, raising=False)
    return fake


@pytest.mark.django_db
def test_permanent_ban_after_24_reminders(vacancy_factory, employer_factory, group_factory, _stub_bot):
    employer = employer_factory()
    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_AWAITING_PAYMENT,
        group=group_factory(),
        extra={
            "unpaid_reminders": 24,
            "unpaid_last_reminder_at": (timezone.now() - _dt.timedelta(hours=2)).isoformat(),
        },
    )

    send_unpaid_reminders_task()
    vacancy.refresh_from_db()

    # Permanent ban created
    block = UserBlock.objects.filter(
        user=employer,
        is_active=True,
        reason=BlockReason.UNPAID,
        block_type=BlockType.PERMANENT,
    ).first()
    assert block is not None
    # User deactivated
    employer.refresh_from_db()
    assert employer.is_active is False
    # Flag set, no duplicate run
    assert vacancy.extra.get("permanent_ban_done") is True
    # Employer got final message
    sent_calls = _stub_bot.send_message.call_args_list
    employer_msgs = [c for c in sent_calls if c.kwargs.get("chat_id") == employer.id]
    assert len(employer_msgs) == 1


@pytest.mark.django_db
def test_permanent_ban_is_idempotent(vacancy_factory, employer_factory, group_factory, _stub_bot):
    """Second invocation must NOT create a second ban."""
    employer = employer_factory()
    vacancy_factory(
        owner=employer,
        status=STATUS_AWAITING_PAYMENT,
        group=group_factory(),
        extra={
            "unpaid_reminders": 24,
            "unpaid_last_reminder_at": (timezone.now() - _dt.timedelta(hours=2)).isoformat(),
            "permanent_ban_done": True,
        },
    )
    UserBlock.objects.create(
        user=employer,
        reason=BlockReason.UNPAID,
        block_type=BlockType.PERMANENT,
        is_active=True,
    )

    send_unpaid_reminders_task()
    # Only the pre-existing block
    assert UserBlock.objects.filter(user=employer, reason=BlockReason.UNPAID, is_active=True).count() == 1


@pytest.mark.django_db
def test_below_24_no_ban(vacancy_factory, employer_factory, group_factory, _stub_bot):
    employer = employer_factory()
    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_AWAITING_PAYMENT,
        group=group_factory(),
        extra={
            "unpaid_reminders": 23,
            "unpaid_last_reminder_at": (timezone.now() - _dt.timedelta(hours=2)).isoformat(),
        },
    )
    send_unpaid_reminders_task()
    assert not UserBlock.objects.filter(
        user=employer, reason=BlockReason.UNPAID, block_type=BlockType.PERMANENT
    ).exists()
    vacancy.refresh_from_db()
    assert vacancy.extra.get("unpaid_reminders") == 24  # this run sent #24
