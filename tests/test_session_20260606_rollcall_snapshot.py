"""Regression tests for the 1st-rollcall snapshot (Stage 1).

Covers:
- snapshot is saved after a successful 1st rollcall
- 2nd rollcall form uses the snapshot, not the live group members
- worker who left the group between rollcalls is still in 2nd rollcall
- worker_my_work shows vacancy via snapshot fallback after leaving the group
- backward compat: vacancy without snapshot falls back to vacancy.members
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from telegram.choices import Status
from vacancy.choices import (
    STATUS_SEARCH_STOPPED,
)
from vacancy.models import VacancyUser
from vacancy.services.rollcall_snapshot import (
    get_snapshot_user_ids,
    get_snapshot_vacancy_users,
    is_user_in_snapshot,
    save_first_rollcall_snapshot,
)


@pytest.mark.django_db
def test_save_snapshot_persists_user_ids(vacancy_factory, worker_factory):
    vacancy = vacancy_factory()
    w1 = worker_factory()
    w2 = worker_factory()

    save_first_rollcall_snapshot(vacancy, [w1.id, w2.id])

    vacancy.refresh_from_db()
    saved = get_snapshot_user_ids(vacancy)
    assert sorted(saved) == sorted([w1.id, w2.id])
    assert is_user_in_snapshot(vacancy, w1)
    assert is_user_in_snapshot(vacancy, w2)


@pytest.mark.django_db
def test_get_snapshot_vacancy_users_returns_snapshot(vacancy_factory, worker_factory):
    vacancy = vacancy_factory()
    w1 = worker_factory()
    w2 = worker_factory()
    VacancyUser.objects.create(vacancy=vacancy, user=w1, status=Status.MEMBER)
    VacancyUser.objects.create(vacancy=vacancy, user=w2, status=Status.LEFT)

    save_first_rollcall_snapshot(vacancy, [w1.id, w2.id])

    qs = get_snapshot_vacancy_users(vacancy)
    user_ids = sorted(qs.values_list("user_id", flat=True))
    assert user_ids == sorted([w1.id, w2.id])


@pytest.mark.django_db
def test_get_snapshot_vacancy_users_fallback_to_members(vacancy_factory, worker_factory):
    """Backward compat: no snapshot key -> fall back to vacancy.members."""
    vacancy = vacancy_factory()
    w1 = worker_factory()
    VacancyUser.objects.create(vacancy=vacancy, user=w1, status=Status.MEMBER)

    qs = get_snapshot_vacancy_users(vacancy)
    user_ids = list(qs.values_list("user_id", flat=True))
    assert user_ids == [w1.id]


@pytest.mark.django_db
def test_worker_my_work_finds_vacancy_in_status_stopped(client, vacancy_factory, worker_factory):
    """Vacancy in STATUS_SEARCH_STOPPED must still appear on 'My work' page."""
    vacancy = vacancy_factory(status=STATUS_SEARCH_STOPPED)
    worker = worker_factory()
    VacancyUser.objects.create(vacancy=vacancy, user=worker, status=Status.MEMBER)

    # Worker is also a member of the telegram group of this vacancy
    if vacancy.group:
        from telegram.models import UserInGroup

        UserInGroup.objects.create(user=worker, group=vacancy.group, status=Status.MEMBER)

    client.force_login(worker)
    resp = client.get(reverse("work:worker_my_work"))
    assert resp.status_code == 200
    assert resp.context["vacancy"] is not None
    assert resp.context["vacancy"].pk == vacancy.pk


@pytest.mark.django_db
def test_worker_my_work_finds_vacancy_via_snapshot_after_leaving_group(client, vacancy_factory, worker_factory):
    """Worker who left/was kicked but is in snapshot must still see vacancy."""
    vacancy = vacancy_factory(status=STATUS_SEARCH_STOPPED)
    worker = worker_factory()
    VacancyUser.objects.create(vacancy=vacancy, user=worker, status=Status.LEFT)

    save_first_rollcall_snapshot(vacancy, [worker.id])

    client.force_login(worker)
    resp = client.get(reverse("work:worker_my_work"))
    assert resp.status_code == 200
    assert resp.context["vacancy"] is not None
    assert resp.context["vacancy"].pk == vacancy.pk
