"""Session 2026-06-03: cleanup window shortened 7d -> 1d for unregistered users."""

from datetime import timedelta

import pytest
from django.utils import timezone

from user.tasks import cleanup_unregistered_users_task


@pytest.mark.django_db
class TestCleanupOneDayWindow:
    """After shortening UNREGISTERED_DAYS to 1, orphan users are cleaned within 24h."""

    def test_orphan_without_profile_deleted_after_25_hours(self):
        """Phone-rejected user (no work_profile) older than 1 day is deleted."""
        from user.models import User

        user = User.objects.create(id=910000001, telegram_id=910000001, username="orphan1")
        User.objects.filter(id=user.id).update(date_joined=timezone.now() - timedelta(hours=25))

        cleanup_unregistered_users_task()

        assert not User.objects.filter(id=910000001).exists()

    def test_orphan_younger_than_24h_kept(self):
        """User younger than 24h is preserved (gives them a chance to register)."""
        from user.models import User

        user = User.objects.create(id=910000002, telegram_id=910000002, username="orphan2")
        User.objects.filter(id=user.id).update(date_joined=timezone.now() - timedelta(hours=23))

        cleanup_unregistered_users_task()

        assert User.objects.filter(id=910000002).exists()

    def test_completed_profile_never_deleted(self):
        """Completed registration survives regardless of age."""
        from tests.factories import WorkerFactory
        from user.models import User

        worker = WorkerFactory(id=910000003, telegram_id=910000003, username="real_user")
        User.objects.filter(id=worker.id).update(date_joined=timezone.now() - timedelta(days=30))

        cleanup_unregistered_users_task()

        assert User.objects.filter(id=910000003).exists()
