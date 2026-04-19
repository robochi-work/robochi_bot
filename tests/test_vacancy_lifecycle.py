"""
Tests for Vacancy model status transitions and basic field integrity.

We do NOT test observer side-effects here (those are in test_observers.py);
we only verify that the ORM layer persists state correctly.
"""

import pytest
from django.utils import timezone


@pytest.mark.django_db
def test_vacancy_created_with_pending_status(vacancy_factory):
    vacancy = vacancy_factory()
    assert vacancy.status == "pending"


@pytest.mark.django_db
def test_vacancy_default_fields(vacancy_factory):
    vacancy = vacancy_factory()

    assert vacancy.group is None
    assert vacancy.channel is None
    assert vacancy.search_active is False
    assert vacancy.closed_at is None
    assert vacancy.people_count == 2


@pytest.mark.django_db
def test_vacancy_pending_to_approved(vacancy_factory, channel_factory, group_factory):
    vacancy = vacancy_factory()
    channel = channel_factory()
    group = group_factory()

    vacancy.status = "approved"
    vacancy.channel = channel
    vacancy.group = group
    vacancy.save()

    vacancy.refresh_from_db()
    assert vacancy.status == "approved"
    assert vacancy.channel_id == channel.id
    assert vacancy.group_id == group.id


@pytest.mark.django_db
def test_vacancy_approved_to_active(vacancy_factory, channel_factory, group_factory):
    vacancy = vacancy_factory(
        status="approved",
        channel=channel_factory(),
        group=group_factory(),
    )

    vacancy.status = "active"
    vacancy.search_active = True
    vacancy.save()

    vacancy.refresh_from_db()
    assert vacancy.status == "active"
    assert vacancy.search_active is True


@pytest.mark.django_db
def test_vacancy_active_to_closed(vacancy_factory, channel_factory, group_factory):
    vacancy = vacancy_factory(
        status="active",
        channel=channel_factory(),
        group=group_factory(),
    )

    now = timezone.now()
    vacancy.status = "closed"
    vacancy.closed_at = now
    vacancy.search_active = False
    vacancy.save()

    vacancy.refresh_from_db()
    assert vacancy.status == "closed"
    assert vacancy.closed_at is not None
    assert vacancy.search_active is False


@pytest.mark.django_db
def test_vacancy_pending_to_rejected(vacancy_factory):
    vacancy = vacancy_factory()

    vacancy.status = "rejected"
    vacancy.save()

    vacancy.refresh_from_db()
    assert vacancy.status == "rejected"


@pytest.mark.django_db
def test_vacancy_owner_relation(vacancy_factory, user_factory):
    owner = user_factory()
    vacancy = vacancy_factory(owner=owner)

    assert vacancy.owner_id == owner.id


@pytest.mark.django_db
def test_multiple_vacancies_per_owner(vacancy_factory, user_factory):
    owner = user_factory()
    v1 = vacancy_factory(owner=owner)
    v2 = vacancy_factory(owner=owner)

    from vacancy.models import Vacancy

    count = Vacancy.objects.filter(owner=owner).count()
    assert count == 2
    assert v1.id != v2.id


@pytest.mark.django_db
def test_vacancy_awaiting_payment_status(vacancy_factory):
    vacancy = vacancy_factory()

    vacancy.status = "awaiting"
    vacancy.save()

    vacancy.refresh_from_db()
    assert vacancy.status == "awaiting"
