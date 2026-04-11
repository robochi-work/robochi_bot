"""
Regression tests for vacancy close/stop lifecycle and status transitions.

Covers:
- close_lifecycle view sets STATUS_CLOSED + cancel_requested
- stop_search sets STATUS_SEARCH_STOPPED + cancel_requested
- STATUS_PAID transition
- Rollcall buttons hidden when closed or no workers
- vacancy_my_list shows closed vacancies within 3h
- get_available_group selects oldest unused group with no active users
"""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone


@pytest.mark.django_db
def test_close_lifecycle_sets_status_closed(vacancy_factory, channel_factory, group_factory):
    vacancy = vacancy_factory(
        status="approved",
        search_active=True,
        channel=channel_factory(),
        group=group_factory(status="process"),
    )
    client = Client(SERVER_NAME="robochi.pp.ua")
    client.force_login(vacancy.owner)
    response = client.post(f"/vacancy/{vacancy.pk}/close-lifecycle/")
    assert response.status_code == 302
    vacancy.refresh_from_db()
    assert vacancy.status == "closed"
    assert vacancy.closed_at is not None
    assert vacancy.search_active is False
    assert vacancy.extra.get("cancel_requested") is True


@pytest.mark.django_db
def test_close_lifecycle_get_redirects(vacancy_factory, channel_factory, group_factory):
    vacancy = vacancy_factory(
        status="approved",
        channel=channel_factory(),
        group=group_factory(status="process"),
    )
    client = Client(SERVER_NAME="robochi.pp.ua")
    client.force_login(vacancy.owner)
    response = client.get(f"/vacancy/{vacancy.pk}/close-lifecycle/")
    assert response.status_code == 302
    vacancy.refresh_from_db()
    assert vacancy.status == "approved"
    assert vacancy.closed_at is None


@pytest.mark.django_db
def test_close_lifecycle_blocked_for_pending(vacancy_factory):
    vacancy = vacancy_factory(status="pending")
    client = Client(SERVER_NAME="robochi.pp.ua")
    client.force_login(vacancy.owner)
    client.post(f"/vacancy/{vacancy.pk}/close-lifecycle/")
    vacancy.refresh_from_db()
    assert vacancy.status == "pending"
    assert vacancy.closed_at is None


@pytest.mark.django_db
def test_close_lifecycle_blocked_for_awaiting(vacancy_factory):
    vacancy = vacancy_factory(status="awaiting")
    client = Client(SERVER_NAME="robochi.pp.ua")
    client.force_login(vacancy.owner)
    client.post(f"/vacancy/{vacancy.pk}/close-lifecycle/")
    vacancy.refresh_from_db()
    assert vacancy.status == "awaiting"


@pytest.mark.django_db
def test_stop_search_sets_stopped(vacancy_factory, channel_factory, group_factory):
    vacancy = vacancy_factory(
        status="approved",
        search_active=True,
        channel=channel_factory(),
        group=group_factory(status="process"),
    )
    client = Client(SERVER_NAME="robochi.pp.ua")
    client.force_login(vacancy.owner)
    response = client.get(f"/vacancy/{vacancy.pk}/stop-search/")
    assert response.status_code == 302
    vacancy.refresh_from_db()
    assert vacancy.status == "stopped"
    assert vacancy.search_active is False
    assert vacancy.search_stopped_at is not None
    assert vacancy.extra.get("cancel_requested") is True


@pytest.mark.django_db
def test_paid_status_transition(vacancy_factory):
    vacancy = vacancy_factory(status="closed")
    vacancy.status = "paid"
    vacancy.extra["is_paid"] = True
    vacancy.save()
    vacancy.refresh_from_db()
    assert vacancy.status == "paid"
    assert vacancy.extra["is_paid"] is True


@pytest.mark.django_db
def test_rollcall_hidden_when_closed(vacancy_factory, channel_factory, group_factory):
    vacancy = vacancy_factory(
        status="closed",
        closed_at=timezone.now(),
        channel=channel_factory(),
        group=group_factory(status="process"),
    )
    client = Client(SERVER_NAME="robochi.pp.ua")
    client.force_login(vacancy.owner)
    response = client.get(f"/vacancy/{vacancy.pk}/detail/")
    content = response.content.decode()
    assert "Перекличка: Початок роботи" not in content


@pytest.mark.django_db
def test_rollcall_hidden_when_no_workers(vacancy_factory, channel_factory, group_factory):
    vacancy = vacancy_factory(
        status="approved",
        search_active=True,
        channel=channel_factory(),
        group=group_factory(status="process"),
    )
    client = Client(SERVER_NAME="robochi.pp.ua")
    client.force_login(vacancy.owner)
    response = client.get(f"/vacancy/{vacancy.pk}/detail/")
    content = response.content.decode()
    assert "Перекличка: Початок роботи" not in content


@pytest.mark.django_db
def test_my_list_shows_recently_closed(vacancy_factory, channel_factory):
    vacancy = vacancy_factory(
        status="closed",
        closed_at=timezone.now() - timedelta(hours=1),
        channel=channel_factory(),
    )
    client = Client(SERVER_NAME="robochi.pp.ua")
    client.force_login(vacancy.owner)
    response = client.get("/vacancy/my/")
    content = response.content.decode()
    assert vacancy.address in content


@pytest.mark.django_db
def test_my_list_hides_old_closed(vacancy_factory, channel_factory):
    vacancy = vacancy_factory(
        status="closed",
        closed_at=timezone.now() - timedelta(hours=4),
        channel=channel_factory(),
    )
    client = Client(SERVER_NAME="robochi.pp.ua")
    client.force_login(vacancy.owner)
    response = client.get("/vacancy/my/")
    content = response.content.decode()
    assert vacancy.address not in content


@pytest.mark.django_db
def test_get_available_group_selects_oldest(group_factory):
    from telegram.service.group import GroupService

    old_group = group_factory(status="available", last_used_at=timezone.now() - timedelta(days=7))
    group_factory(status="available", last_used_at=timezone.now() - timedelta(hours=1))
    result = GroupService.get_available_group()
    assert result is not None
    assert result.id == old_group.id


@pytest.mark.django_db
def test_get_available_group_skips_groups_with_users(group_factory, user_factory):
    from telegram.models import UserInGroup
    from telegram.service.group import GroupService

    dirty_group = group_factory(status="available", last_used_at=timezone.now() - timedelta(days=7))
    clean_group = group_factory(status="available", last_used_at=timezone.now() - timedelta(days=1))
    user = user_factory()
    UserInGroup.objects.create(group=dirty_group, user=user, status="member")
    result = GroupService.get_available_group()
    assert result is not None
    assert result.id == clean_group.id


@pytest.mark.django_db
def test_closed_status_label(vacancy_factory, channel_factory):
    vacancy = vacancy_factory(status="closed", closed_at=timezone.now(), channel=channel_factory())
    client = Client(SERVER_NAME="robochi.pp.ua")
    client.force_login(vacancy.owner)
    response = client.get(f"/vacancy/{vacancy.pk}/detail/")
    content = response.content.decode()
    assert "Закрита" in content
