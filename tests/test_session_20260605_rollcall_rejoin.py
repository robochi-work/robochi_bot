"""
Regression tests for session 2026-06-05:
- BEFORE_START rollcall must NOT re-kick a worker who was kicked, unblocked
  by admin, and re-joined (stale VacancyUserCall must be ignored).
- BEFORE_START kick must finalize the call (status=REJECT) so the same record
  cannot re-trigger.
- Concurrent vacancy publishes (Celery rotation + Telegram slot_freed) must
  not produce a duplicate channel post — a short cache-based mutex protects.
"""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.utils import timezone

from telegram.choices import CallStatus, CallType, Status
from telegram.models import UserInGroup
from vacancy.choices import STATUS_APPROVED
from vacancy.models import VacancyUser, VacancyUserCall
from vacancy.services.observers.call_observer import VacancyBeforeCallObserver


def _make_vacancy_with_member(worker_factory, vacancy_factory, group_factory):
    worker = worker_factory()
    group = group_factory()
    now = timezone.now()
    start_time_local = (now + timedelta(minutes=30)).astimezone(timezone.get_current_timezone()).time()
    vacancy = vacancy_factory(
        owner=worker_factory(),
        status=STATUS_APPROVED,
        group=group,
        date=date.today(),
        start_time=start_time_local,
    )
    vu = VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.MEMBER)
    UserInGroup.objects.create(user=worker, group=group, status=Status.MEMBER)
    return worker, vacancy, vu


@pytest.mark.django_db
class TestBeforeStartNoRekickOnRejoin:
    """check_before_5_start must NOT re-kick a worker who rejoined after the rollcall."""

    def test_skips_worker_who_rejoined_after_call_sent(self, worker_factory, vacancy_factory, group_factory):
        worker, vacancy, vu = _make_vacancy_with_member(worker_factory, vacancy_factory, group_factory)
        now = timezone.now()
        # Old BEFORE_START call (sent 1h ago, never answered)
        call = VacancyUserCall.objects.create(
            vacancy_user=vu,
            call_type=CallType.BEFORE_START.value,
            status=CallStatus.SENT.value,
        )
        VacancyUserCall.objects.filter(pk=call.pk).update(created_at=now - timedelta(hours=1))
        # Worker re-joined: updated_at is fresher than the call.created_at
        VacancyUser.objects.filter(pk=vu.pk).update(updated_at=now)

        with (
            patch("vacancy.services.observers.call_observer.GroupService.kick_user") as kick_mock,
            patch("vacancy.services.observers.call_observer.BlockService.auto_block_rollcall_reject") as block_mock,
            patch("vacancy.services.observers.call_observer.get_bot"),
        ):
            VacancyBeforeCallObserver.check_before_5_start(vacancy)

        assert not kick_mock.called, "Worker who rejoined after old rollcall must NOT be re-kicked"
        assert not block_mock.called, "No auto-block on rejoin"
        # Old call must remain untouched (still SENT)
        call.refresh_from_db()
        assert call.status == CallStatus.SENT.value

    def test_skips_when_call_already_rejected(self, worker_factory, vacancy_factory, group_factory):
        worker, vacancy, vu = _make_vacancy_with_member(worker_factory, vacancy_factory, group_factory)
        now = timezone.now()
        call = VacancyUserCall.objects.create(
            vacancy_user=vu,
            call_type=CallType.BEFORE_START.value,
            status=CallStatus.REJECT.value,
        )
        VacancyUserCall.objects.filter(pk=call.pk).update(created_at=now - timedelta(hours=1))
        VacancyUser.objects.filter(pk=vu.pk).update(updated_at=now - timedelta(hours=2))

        with (
            patch("vacancy.services.observers.call_observer.GroupService.kick_user") as kick_mock,
            patch("vacancy.services.observers.call_observer.BlockService.auto_block_rollcall_reject"),
            patch("vacancy.services.observers.call_observer.get_bot"),
        ):
            VacancyBeforeCallObserver.check_before_5_start(vacancy)

        assert not kick_mock.called, "Finalized REJECT call must not trigger another kick"

    def test_kick_finalizes_call_status_to_reject(self, worker_factory, vacancy_factory, group_factory):
        """When kicking for rollcall ignore, the call must become REJECT."""
        worker, vacancy, vu = _make_vacancy_with_member(worker_factory, vacancy_factory, group_factory)
        now = timezone.now()
        # Stale call, worker DID NOT rejoin (updated_at older than created_at)
        call = VacancyUserCall.objects.create(
            vacancy_user=vu,
            call_type=CallType.BEFORE_START.value,
            status=CallStatus.SENT.value,
        )
        VacancyUserCall.objects.filter(pk=call.pk).update(created_at=now - timedelta(minutes=10))
        VacancyUser.objects.filter(pk=vu.pk).update(updated_at=now - timedelta(hours=2))

        with (
            patch("vacancy.services.observers.call_observer.GroupService.kick_user") as kick_mock,
            patch("vacancy.services.observers.call_observer.BlockService.auto_block_rollcall_reject") as block_mock,
            patch("vacancy.services.observers.call_observer.BlockService.is_blocked", return_value=False),
            patch("vacancy.services.observers.call_observer.get_bot"),
            patch("vacancy.services.observers.call_observer.delete_bot_message"),
        ):
            VacancyBeforeCallObserver.check_before_5_start(vacancy)

        assert kick_mock.called, "Stale SENT call past KICK_AFTER must trigger kick"
        assert block_mock.called, "Auto-block must be issued on kick"
        call.refresh_from_db()
        assert call.status == CallStatus.REJECT.value, "Call must be finalized to REJECT"


@pytest.mark.django_db
class TestChannelPublishMutex:
    """Concurrent rotation + slot_freed must not double-publish a vacancy."""

    def setup_method(self):
        cache.clear()

    def teardown_method(self):
        cache.clear()

    def test_rotation_skips_when_lock_held(self, vacancy_factory, channel_factory, group_factory):
        from vacancy.tasks.resend import resend_vacancy_to_channel

        channel = channel_factory()
        group = group_factory()
        vacancy = vacancy_factory(status=STATUS_APPROVED, group=group, channel=channel)
        # Simulate slot_freed already running
        cache.add(f"vacancy_publish_lock:{vacancy.id}", True, timeout=15)

        with (
            patch("vacancy.tasks.resend.MessageDeleter"),
            patch("vacancy.tasks.resend.MessageDeleteService"),
            patch("vacancy.tasks.resend.TelegramNotifier") as notifier_mock,
        ):
            resend_vacancy_to_channel(vacancy)

        assert not notifier_mock.return_value.notify.called, (
            "Rotation must NOT publish while another path holds the lock"
        )

    def test_rotation_publishes_when_lock_free(self, vacancy_factory, channel_factory, group_factory):
        from vacancy.tasks.resend import resend_vacancy_to_channel

        channel = channel_factory()
        group = group_factory()
        vacancy = vacancy_factory(status=STATUS_APPROVED, group=group, channel=channel)

        with (
            patch("vacancy.tasks.resend.MessageDeleter"),
            patch("vacancy.tasks.resend.MessageDeleteService"),
            patch("vacancy.tasks.resend.TelegramNotifier") as notifier_mock,
        ):
            resend_vacancy_to_channel(vacancy)

        assert notifier_mock.return_value.notify.called, "Rotation must publish when lock is free"
        # Lock must be released after the call
        assert cache.get(f"vacancy_publish_lock:{vacancy.id}") is None
