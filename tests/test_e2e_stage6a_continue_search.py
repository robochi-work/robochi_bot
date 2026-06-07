"""End-to-end integration test for Stage 6.A.

Walks through the full HTTP flow:
1. Employer opens vacancy_detail in rollcall mode (1st rollcall, scenario B).
2. Clicks "Підтвердити наявних + шукати ще" → GET /continue-search/?confirm_rollcall=1.
3. Reloads vacancy_detail → sees the "Триває добір" banner.
4. New worker joins the group during the 1h window.
5. Celery task fires (simulated) → snapshot saved, vacancy moved to SEARCH_STOPPED.
6. Reloads vacancy_detail → banner is gone, vacancy in normal post-rollcall state.

This complements the unit tests in test_continue_search_bug_07062026.py — those
exercise the service layer directly; this one drives the view layer over HTTP.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from telegram.choices import Status
from vacancy.choices import STATUS_APPROVED, STATUS_SEARCH_STOPPED
from vacancy.models import VacancyUser
from vacancy.services.continue_after_rollcall import (
    finalize_continue_after_first_rollcall,
    is_in_continue_mode,
)
from vacancy.services.rollcall_snapshot import get_snapshot_user_ids


@pytest.mark.django_db
def test_e2e_continue_search_after_first_rollcall(
    client, vacancy_factory, employer_factory, worker_factory, group_factory
):
    employer = employer_factory()
    group = group_factory()
    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_APPROVED,
        group=group,
        people_count=5,
        first_rollcall_passed=False,
        search_active=True,
    )

    initial_workers = []
    for _ in range(2):
        w = worker_factory()
        VacancyUser.objects.create(vacancy=vacancy, user=w, status=Status.MEMBER)
        initial_workers.append(w)

    client.force_login(employer)
    detail_url = reverse("vacancy:detail", kwargs={"pk": vacancy.pk})

    # ── Step 1: Open vacancy_detail in rollcall mode (scenario B) ────────────
    resp = client.get(detail_url)
    assert resp.status_code == 200, "Detail page must open"
    ctx = resp.context
    assert ctx["is_start_rollcall"] is True, "1st rollcall must be active"
    assert ctx["scenario"] == "B", "Scenario B: workers exist but not enough"
    assert ctx.get("continue_mode") is False, "Not in continue-mode yet"

    # ── Step 2: Click "Підтвердити наявних + шукати ще" ──────────────────────
    confirm_url = reverse("vacancy:continue_search", kwargs={"pk": vacancy.pk}) + "?confirm_rollcall=1"
    resp = client.get(confirm_url)
    assert resp.status_code in (200, 302), "Confirm-and-continue must redirect or render"

    vacancy.refresh_from_db()
    assert vacancy.first_rollcall_passed is True
    assert is_in_continue_mode(vacancy)
    assert vacancy.extra.get("continue_deadline")
    # Snapshot intentionally deferred
    assert get_snapshot_user_ids(vacancy) == []

    # ── Step 3: Reload detail page → banner must be present ──────────────────
    resp = client.get(detail_url)
    assert resp.status_code == 200
    ctx = resp.context
    assert ctx["continue_mode"] is True, "Banner flag must be in context"
    assert ctx["continue_ends_at"] is not None, "Deadline timestamp must be in context"
    assert ctx["is_start_rollcall"] is False, "1st rollcall is now passed"
    body = resp.content.decode("utf-8")
    assert "Триває добір працівників" in body, "Banner heading must render in HTML"
    assert "data-continue-remaining" in body, "JS countdown placeholder must render"

    # ── Step 4: A new worker joins during the 1h window ──────────────────────
    new_worker = worker_factory()
    VacancyUser.objects.create(vacancy=vacancy, user=new_worker, status=Status.MEMBER)

    # ── Step 5: Celery task fires at deadline (simulated) ────────────────────
    result = finalize_continue_after_first_rollcall(vacancy)
    assert result["action"] == "finalized"
    assert result["members"] == 3  # 2 initial + 1 late joiner

    vacancy.refresh_from_db()
    assert vacancy.status == STATUS_SEARCH_STOPPED
    assert vacancy.search_active is False
    assert not is_in_continue_mode(vacancy)
    expected_ids = {w.id for w in initial_workers} | {new_worker.id}
    assert set(get_snapshot_user_ids(vacancy)) == expected_ids, (
        "Snapshot must contain ALL members at finalization time, including the late joiner"
    )

    # ── Step 6: Reload detail page → banner is gone ──────────────────────────
    resp = client.get(detail_url)
    assert resp.status_code == 200
    ctx = resp.context
    assert ctx["continue_mode"] is False, "Banner must disappear after finalization"
    body = resp.content.decode("utf-8")
    assert "Триває добір" not in body, "Banner HTML must not render"
