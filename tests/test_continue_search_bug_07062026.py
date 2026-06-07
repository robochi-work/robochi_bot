"""Regression tests for Stage 6.A: continue-search after 1st rollcall.

Covers the 4 scenarios for "Підтвердити наявних + шукати ще" button + bonus edge case:

1. Limit reached during 1h window → finalize via Celery task → all members snapshotted.
2. Nobody came in 1h → finalize → snapshot = original members, admin notified (scenario_b).
3. Some came but not enough → finalize → admin notified (scenario_b).
4. Employer pressed "Зупинити пошук" with ≥1 worker → finalize immediately.
5. (Edge case) Employer pressed "Зупинити пошук" with 0 workers → auto-close as CLOSED.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from telegram.choices import CallStatus, CallType, Status
from vacancy.choices import STATUS_APPROVED, STATUS_CLOSED, STATUS_SEARCH_STOPPED
from vacancy.models import VacancyUser, VacancyUserCall
from vacancy.services.continue_after_rollcall import (
    finalize_continue_after_first_rollcall,
    is_in_continue_mode,
)
from vacancy.services.rollcall_snapshot import get_snapshot_user_ids

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_vacancy_with_members(
    *,
    vacancy_factory,
    employer_factory,
    worker_factory,
    group_factory,
    member_count: int,
    people_count: int,
):
    """Create approved vacancy with N MEMBER workers in group."""
    employer = employer_factory()
    group = group_factory()
    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_APPROVED,
        group=group,
        people_count=people_count,
        first_rollcall_passed=False,
        search_active=True,
    )
    workers = []
    for _ in range(member_count):
        w = worker_factory()
        VacancyUser.objects.create(vacancy=vacancy, user=w, status=Status.MEMBER)
        workers.append(w)
    return employer, vacancy, workers


def _press_confirm_and_continue(client, employer, vacancy):
    """Simulate the employer clicking 'Підтвердити наявних + шукати ще'."""
    client.force_login(employer)
    url = reverse("vacancy:continue_search", kwargs={"pk": vacancy.pk}) + "?confirm_rollcall=1"
    return client.get(url)


# ─── Test: GET ?confirm_rollcall=1 sets continue-mode but defers snapshot ─────


@pytest.mark.django_db
def test_confirm_rollcall_sets_continue_mode_but_defers_snapshot(
    client, vacancy_factory, employer_factory, worker_factory, group_factory
):
    """The button must:
    - Set first_rollcall_passed=True (stop reminders).
    - Set extra["continue_after_first_rollcall"]=True + deadline.
    - NOT save snapshot yet (snapshot is saved AT finalization).
    """
    employer, vacancy, workers = _make_vacancy_with_members(
        vacancy_factory=vacancy_factory,
        employer_factory=employer_factory,
        worker_factory=worker_factory,
        group_factory=group_factory,
        member_count=3,
        people_count=5,
    )

    resp = _press_confirm_and_continue(client, employer, vacancy)
    assert resp.status_code in (200, 302)

    vacancy.refresh_from_db()
    assert vacancy.first_rollcall_passed is True
    assert is_in_continue_mode(vacancy)
    assert vacancy.extra.get("continue_deadline")
    # Snapshot is intentionally NOT saved yet
    assert get_snapshot_user_ids(vacancy) == []


# ─── Scenario 1: Limit reached → finalize → all members in snapshot ──────────


@pytest.mark.django_db
def test_scenario_1_limit_reached_during_continue(
    client, vacancy_factory, employer_factory, worker_factory, group_factory
):
    """Workers fill up the slot during the 1h window → finalize via task →
    snapshot contains ALL current members (limit-reached just stops channel
    button, the finalize task still runs at deadline)."""
    employer, vacancy, original_workers = _make_vacancy_with_members(
        vacancy_factory=vacancy_factory,
        employer_factory=employer_factory,
        worker_factory=worker_factory,
        group_factory=group_factory,
        member_count=3,
        people_count=5,
    )

    _press_confirm_and_continue(client, employer, vacancy)
    vacancy.refresh_from_db()

    # Simulate 2 more workers joining during 1h window
    extra_workers = []
    for _ in range(2):
        w = worker_factory()
        VacancyUser.objects.create(vacancy=vacancy, user=w, status=Status.MEMBER)
        extra_workers.append(w)

    # Simulate Celery task firing at the deadline
    result = finalize_continue_after_first_rollcall(vacancy)
    vacancy.refresh_from_db()

    assert result["action"] == "finalized"
    assert result["members"] == 5
    expected_ids = {w.id for w in original_workers + extra_workers}
    assert set(get_snapshot_user_ids(vacancy)) == expected_ids
    assert vacancy.status == STATUS_SEARCH_STOPPED
    assert vacancy.search_active is False
    assert not is_in_continue_mode(vacancy)


# ─── Scenario 2: Nobody came → finalize → original members in snapshot ───────


@pytest.mark.django_db
def test_scenario_2_no_new_workers(client, vacancy_factory, employer_factory, worker_factory, group_factory):
    """Nobody joined during 1h → finalize → snapshot = original 2 workers,
    status SEARCH_STOPPED. Plan was 5, got 2 → scenario_b admin notification."""
    employer, vacancy, original_workers = _make_vacancy_with_members(
        vacancy_factory=vacancy_factory,
        employer_factory=employer_factory,
        worker_factory=worker_factory,
        group_factory=group_factory,
        member_count=2,
        people_count=5,
    )

    _press_confirm_and_continue(client, employer, vacancy)
    vacancy.refresh_from_db()

    result = finalize_continue_after_first_rollcall(vacancy)
    vacancy.refresh_from_db()

    assert result["action"] == "finalized"
    assert result["members"] == 2
    assert set(get_snapshot_user_ids(vacancy)) == {w.id for w in original_workers}
    assert vacancy.status == STATUS_SEARCH_STOPPED


# ─── Scenario 3: Some new workers but still not enough ────────────────────────


@pytest.mark.django_db
def test_scenario_3_partial_fill(client, vacancy_factory, employer_factory, worker_factory, group_factory):
    """1 new worker joined, but still 3<5 → finalize → snapshot has 3,
    admin notified (scenario_b)."""
    employer, vacancy, original_workers = _make_vacancy_with_members(
        vacancy_factory=vacancy_factory,
        employer_factory=employer_factory,
        worker_factory=worker_factory,
        group_factory=group_factory,
        member_count=2,
        people_count=5,
    )

    _press_confirm_and_continue(client, employer, vacancy)
    vacancy.refresh_from_db()

    new_worker = worker_factory()
    VacancyUser.objects.create(vacancy=vacancy, user=new_worker, status=Status.MEMBER)

    result = finalize_continue_after_first_rollcall(vacancy)
    vacancy.refresh_from_db()

    assert result["action"] == "finalized"
    assert result["members"] == 3
    expected_ids = {w.id for w in original_workers} | {new_worker.id}
    assert set(get_snapshot_user_ids(vacancy)) == expected_ids


# ─── Scenario 4: Employer pressed "Зупинити пошук" with ≥1 worker ────────────


@pytest.mark.django_db
def test_scenario_4_stop_search_with_workers(client, vacancy_factory, employer_factory, worker_factory, group_factory):
    """Employer presses 'Зупинити пошук' during 1h window with ≥1 worker.
    Snapshot is saved immediately, Celery task (if it fires later) is a noop."""
    employer, vacancy, original_workers = _make_vacancy_with_members(
        vacancy_factory=vacancy_factory,
        employer_factory=employer_factory,
        worker_factory=worker_factory,
        group_factory=group_factory,
        member_count=2,
        people_count=5,
    )

    _press_confirm_and_continue(client, employer, vacancy)
    vacancy.refresh_from_db()

    # Press "Зупинити пошук"
    url = reverse("vacancy:stop_search", kwargs={"pk": vacancy.pk})
    resp = client.get(url)
    assert resp.status_code in (200, 302)

    vacancy.refresh_from_db()
    assert vacancy.status == STATUS_SEARCH_STOPPED
    assert set(get_snapshot_user_ids(vacancy)) == {w.id for w in original_workers}
    assert not is_in_continue_mode(vacancy)

    # Idempotency: a second finalize call (e.g. delayed Celery task) is a noop
    result2 = finalize_continue_after_first_rollcall(vacancy)
    assert result2["action"] == "noop"


# ─── Edge case: stop_search with 0 workers → auto-close ──────────────────────


@pytest.mark.django_db
def test_edge_stop_search_zero_workers_auto_closes(
    client, vacancy_factory, employer_factory, worker_factory, group_factory
):
    """Vacancy goes into continue-mode (group had ≥1 worker at button press),
    but by the time employer presses 'Зупинити пошук', group is empty (everyone left).
    Expected: auto-close as CLOSED (Закрити вакансію behavior)."""
    employer, vacancy, original_workers = _make_vacancy_with_members(
        vacancy_factory=vacancy_factory,
        employer_factory=employer_factory,
        worker_factory=worker_factory,
        group_factory=group_factory,
        member_count=1,
        people_count=5,
    )

    _press_confirm_and_continue(client, employer, vacancy)

    # All members leave the group before employer presses stop
    VacancyUser.objects.filter(vacancy=vacancy).update(status=Status.LEFT)
    vacancy.refresh_from_db()

    url = reverse("vacancy:stop_search", kwargs={"pk": vacancy.pk})
    resp = client.get(url)
    assert resp.status_code in (200, 302)

    vacancy.refresh_from_db()
    assert vacancy.status == STATUS_CLOSED
    assert vacancy.closed_at is not None
    assert vacancy.search_active is False
    assert not is_in_continue_mode(vacancy)


# ─── Finalization details: VacancyUserCall records marked CONFIRM ────────────


@pytest.mark.django_db
def test_finalize_marks_vacancyusercalls_confirm(
    client, vacancy_factory, employer_factory, worker_factory, group_factory
):
    """After finalization, each member must have a VacancyUserCall(START, CONFIRM)."""
    employer, vacancy, workers = _make_vacancy_with_members(
        vacancy_factory=vacancy_factory,
        employer_factory=employer_factory,
        worker_factory=worker_factory,
        group_factory=group_factory,
        member_count=3,
        people_count=5,
    )
    _press_confirm_and_continue(client, employer, vacancy)
    vacancy.refresh_from_db()
    finalize_continue_after_first_rollcall(vacancy)

    confirmed = VacancyUserCall.objects.filter(
        vacancy_user__vacancy=vacancy,
        call_type=CallType.START,
        status=CallStatus.CONFIRM,
    ).count()
    assert confirmed == 3
