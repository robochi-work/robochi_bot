"""Regression tests for user cleanup tasks (session 2026-05-07)."""

from datetime import time, timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from user.tasks import (
    cleanup_inactive_users_task,
    cleanup_unregistered_users_task,
)


def _create_vacancy(owner, days_ago=0):
    """Helper to create a valid Vacancy."""
    from vacancy.models import Vacancy

    return Vacancy.objects.create(
        owner=owner,
        people_count=1,
        has_passport=False,
        address="test address",
        date=timezone.now().date() - timedelta(days=days_ago),
        start_time=time(9, 0),
        end_time=time(18, 0),
        payment_amount=500,
        skills="test",
    )


@pytest.mark.django_db
class TestCleanupUnregisteredUsers:
    """Task 1: delete users who pressed /start but never entered cabinet within 7 days."""

    def test_deletes_user_without_profile_after_7_days(self):
        from user.models import User

        user = User.objects.create(id=900000001, telegram_id=900000001, username="ghost1")
        User.objects.filter(id=user.id).update(date_joined=timezone.now() - timedelta(days=8))
        cleanup_unregistered_users_task()
        assert not User.objects.filter(id=900000001).exists()

    def test_keeps_user_without_profile_before_7_days(self):
        from user.models import User

        user = User.objects.create(id=900000002, telegram_id=900000002, username="fresh1")
        User.objects.filter(id=user.id).update(date_joined=timezone.now() - timedelta(days=3))
        cleanup_unregistered_users_task()
        assert User.objects.filter(id=900000002).exists()

    def test_deletes_user_with_incomplete_profile_after_7_days(self):
        from tests.factories import WorkerFactory
        from user.models import User

        worker = WorkerFactory(id=900000003, telegram_id=900000003, username="incomplete1")
        worker.work_profile.is_completed = False
        worker.work_profile.save()
        User.objects.filter(id=worker.id).update(date_joined=timezone.now() - timedelta(days=10))
        cleanup_unregistered_users_task()
        assert not User.objects.filter(id=900000003).exists()

    def test_keeps_completed_user(self):
        from tests.factories import WorkerFactory
        from user.models import User

        worker = WorkerFactory(id=900000004, telegram_id=900000004, username="complete1")
        User.objects.filter(id=worker.id).update(date_joined=timezone.now() - timedelta(days=30))
        cleanup_unregistered_users_task()
        assert User.objects.filter(id=900000004).exists()

    def test_does_not_delete_staff(self):
        from user.models import User

        user = User.objects.create(id=900000005, telegram_id=900000005, username="admin1", is_staff=True)
        User.objects.filter(id=user.id).update(date_joined=timezone.now() - timedelta(days=30))
        cleanup_unregistered_users_task()
        assert User.objects.filter(id=900000005).exists()


@pytest.mark.django_db
class TestCleanupInactiveWorker:
    """Task 3: workers inactive for 180 days get deleted."""

    @patch("user.tasks.check_telegram_deleted", return_value=False)
    def test_deletes_inactive_worker(self, mock_tg):
        from tests.factories import WorkerFactory
        from user.models import User

        worker = WorkerFactory(id=900000010, telegram_id=900000010, username="oldworker")
        User.objects.filter(id=worker.id).update(date_joined=timezone.now() - timedelta(days=200))
        cleanup_inactive_users_task()
        assert not User.objects.filter(id=900000010).exists()

    @patch("user.tasks.check_telegram_deleted", return_value=False)
    def test_keeps_worker_with_recent_vacancy(self, mock_tg):
        from tests.factories import EmployerFactory, WorkerFactory
        from user.models import User
        from vacancy.models import VacancyUser

        worker = WorkerFactory(id=900000011, telegram_id=900000011, username="activeworker")
        User.objects.filter(id=worker.id).update(date_joined=timezone.now() - timedelta(days=200))
        employer = EmployerFactory(id=900000099, telegram_id=900000099)
        vacancy = _create_vacancy(employer)
        VacancyUser.objects.create(user=worker, vacancy=vacancy)
        cleanup_inactive_users_task()
        assert User.objects.filter(id=900000011).exists()


@pytest.mark.django_db
class TestCleanupInactiveEmployer:
    """Task 5: employers inactive for 180 days get deleted."""

    @patch("user.tasks.check_telegram_deleted", return_value=False)
    def test_deletes_inactive_employer(self, mock_tg):
        from tests.factories import EmployerFactory
        from user.models import User

        employer = EmployerFactory(id=900000020, telegram_id=900000020, username="oldemployer")
        User.objects.filter(id=employer.id).update(date_joined=timezone.now() - timedelta(days=200))
        cleanup_inactive_users_task()
        assert not User.objects.filter(id=900000020).exists()

    @patch("user.tasks.check_telegram_deleted", return_value=False)
    def test_keeps_employer_with_recent_vacancy(self, mock_tg):
        from tests.factories import EmployerFactory
        from user.models import User

        employer = EmployerFactory(id=900000021, telegram_id=900000021, username="activeemployer")
        User.objects.filter(id=employer.id).update(date_joined=timezone.now() - timedelta(days=200))
        _create_vacancy(employer)
        cleanup_inactive_users_task()
        assert User.objects.filter(id=900000021).exists()


@pytest.mark.django_db
class TestCleanupDeletedTelegramAccount:
    """Task 4: users with deleted Telegram accounts get deleted from DB."""

    @patch("user.tasks.check_telegram_deleted", return_value=True)
    def test_deletes_user_with_deleted_telegram(self, mock_tg):
        from tests.factories import WorkerFactory
        from user.models import User

        WorkerFactory(id=900000030, telegram_id=900000030, username="deletedtg")
        cleanup_inactive_users_task()
        assert not User.objects.filter(id=900000030).exists()

    @patch("user.tasks.check_telegram_deleted", return_value=False)
    def test_keeps_user_with_active_telegram(self, mock_tg):
        from tests.factories import WorkerFactory
        from user.models import User

        WorkerFactory(id=900000031, telegram_id=900000031, username="activetg")
        cleanup_inactive_users_task()
        assert User.objects.filter(id=900000031).exists()
