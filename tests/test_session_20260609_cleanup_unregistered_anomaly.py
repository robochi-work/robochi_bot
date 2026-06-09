"""Regression test for cleanup_unregistered_users_task (09.06.2026, v2).

Design: this task deletes users who pressed /start but never finished
registration (within UNREGISTERED_DAYS=1). By design these users:
- have is_completed=False
- have no role/city
- cannot create vacancies or join groups

If a deletion candidate DOES have vacancy links → that signals a data
integrity bug elsewhere (is_completed never set to True for a real user).
In that case the task must SKIP deletion and alert admins, not silently
wipe data.
"""

from datetime import timedelta

import pytest
from django.utils import timezone


def test_unregistered_days_is_one():
    """1-day grace is the intended design for this task."""
    from user.tasks import UNREGISTERED_DAYS

    assert UNREGISTERED_DAYS == 1


@pytest.mark.django_db
def test_truly_abandoned_user_is_deleted():
    """User with no profile, no phone, no vacancies, >1 day old → deleted."""
    from user.models import User
    from user.tasks import cleanup_unregistered_users_task

    User.objects.create(
        id=999333,
        username="truly_abandoned",
        date_joined=timezone.now() - timedelta(days=2),
    )

    cleanup_unregistered_users_task()

    assert not User.objects.filter(id=999333).exists()


@pytest.mark.django_db
def test_user_with_incomplete_profile_is_deleted():
    """User who started wizard but didn't finish (profile exists, is_completed=False) → deleted."""
    from user.models import User
    from user.tasks import cleanup_unregistered_users_task
    from work.models import UserWorkProfile

    user = User.objects.create(
        id=999334,
        username="halfreg_no_data",
        date_joined=timezone.now() - timedelta(days=2),
    )
    UserWorkProfile.objects.create(user=user, is_completed=False)

    cleanup_unregistered_users_task()

    assert not User.objects.filter(id=999334).exists()


@pytest.mark.django_db
def test_completed_user_is_preserved():
    """Fully registered user (is_completed=True) must never be touched."""
    from user.models import User
    from user.tasks import cleanup_unregistered_users_task
    from work.models import UserWorkProfile

    user = User.objects.create(
        id=999335,
        username="fully_registered",
        date_joined=timezone.now() - timedelta(days=14),
    )
    UserWorkProfile.objects.create(user=user, is_completed=True)

    cleanup_unregistered_users_task()

    assert User.objects.filter(id=999335).exists()


@pytest.mark.django_db
def test_user_within_grace_period_is_preserved():
    """Less than 1 day since join — too early to clean up."""
    from user.models import User
    from user.tasks import cleanup_unregistered_users_task

    User.objects.create(
        id=999336,
        username="fresh",
        date_joined=timezone.now() - timedelta(hours=12),
    )

    cleanup_unregistered_users_task()

    assert User.objects.filter(id=999336).exists()


@pytest.mark.django_db
def test_anomaly_unregistered_with_vacancy_owned_is_preserved(monkeypatch):
    """ANOMALY: unregistered user owns a vacancy → must SKIP delete + alert admins."""
    from user.models import User
    from user.tasks import cleanup_unregistered_users_task
    from vacancy.models import Vacancy
    from work.models import UserWorkProfile

    alerted = {"called": False}
    monkeypatch.setattr(
        "service.broadcast_service.TelegramBroadcastService.admin_broadcast",
        lambda self, **kwargs: alerted.update(called=True),
    )

    user = User.objects.create(
        id=999337,
        username="anomaly_owner",
        date_joined=timezone.now() - timedelta(days=2),
    )
    UserWorkProfile.objects.create(user=user, is_completed=False)
    Vacancy.objects.create(
        owner=user,
        people_count=1,
        has_passport=False,
        address="test",
        date=timezone.now().date(),
        start_time="10:00",
        end_time="13:00",
        payment_amount=100,
        skills="test",
    )

    cleanup_unregistered_users_task()

    assert User.objects.filter(id=999337).exists(), "Anomalous user with vacancy must NOT be deleted"
    assert alerted["called"], "Admin alert must be sent for the anomaly"


@pytest.mark.django_db
def test_anomaly_unregistered_with_vacancy_user_link_is_preserved(monkeypatch):
    """ANOMALY: unregistered user has VacancyUser link → must SKIP + alert."""
    from telegram.choices import Status
    from user.models import User
    from user.tasks import cleanup_unregistered_users_task
    from vacancy.models import Vacancy, VacancyUser
    from work.models import UserWorkProfile

    monkeypatch.setattr(
        "service.broadcast_service.TelegramBroadcastService.admin_broadcast",
        lambda self, **kwargs: None,
    )

    owner = User.objects.create(id=999338, username="owner_x")
    UserWorkProfile.objects.create(user=owner, is_completed=True)

    user = User.objects.create(
        id=999339,
        username="anomaly_member",
        date_joined=timezone.now() - timedelta(days=2),
    )
    UserWorkProfile.objects.create(user=user, is_completed=False)

    vacancy = Vacancy.objects.create(
        owner=owner,
        people_count=1,
        has_passport=False,
        address="test",
        date=timezone.now().date(),
        start_time="10:00",
        end_time="13:00",
        payment_amount=100,
        skills="test",
    )
    VacancyUser.objects.create(vacancy=vacancy, user=user, status=Status.MEMBER)

    cleanup_unregistered_users_task()

    assert User.objects.filter(id=999339).exists()
