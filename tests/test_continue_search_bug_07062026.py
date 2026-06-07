"""Regression test for the continue_search bug discovered on 07.06.2026.

The bug: button "Підтвердити наявних + шукати ще" links to
vacancy:continue_search?confirm_rollcall=1, but the ?confirm_rollcall=1 handler
lives in vacancy_resume_search, not vacancy_continue_search.

As a result:
- first_rollcall_passed is reset to False
- snapshot is NEVER saved
- all VacancyUserCall records are deleted
- the cycle starts from scratch instead of confirming the 1st rollcall

This is XFAIL until Stage 6.A reworks the flow.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from telegram.choices import Status
from vacancy.choices import STATUS_APPROVED
from vacancy.models import VacancyUser
from vacancy.services.rollcall_snapshot import get_snapshot_user_ids


@pytest.mark.django_db
@pytest.mark.xfail(
    reason="Stage 6.A: continue_search?confirm_rollcall=1 does not save snapshot. "
    "Button is wired to wrong view. Will be fixed by new view "
    "vacancy_confirm_and_continue_search.",
    strict=True,
)
def test_continue_search_with_confirm_rollcall_saves_snapshot(
    client, vacancy_factory, employer_factory, worker_factory, group_factory
):
    """When employer presses 'Підтвердити наявних + шукати ще':
    - current MEMBER workers should be saved into snapshot
    - first_rollcall_passed should become True
    - search should continue with a 1h refind window
    """
    employer = employer_factory()
    group = group_factory()
    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_APPROVED,
        group=group,
        people_count=5,
        first_rollcall_passed=False,
    )

    # 3 workers currently in group (less than needed)
    workers = []
    for _ in range(3):
        w = worker_factory()
        VacancyUser.objects.create(vacancy=vacancy, user=w, status=Status.MEMBER)
        workers.append(w)

    client.force_login(employer)
    url = reverse("vacancy:continue_search", kwargs={"pk": vacancy.pk}) + "?confirm_rollcall=1"
    resp = client.get(url)
    assert resp.status_code in (200, 302)

    vacancy.refresh_from_db()
    # CURRENTLY FAILS — Stage 6.A will fix this:
    assert vacancy.first_rollcall_passed is True, (
        "1st rollcall must be auto-confirmed when employer presses 'шукати ще'"
    )
    snapshot_ids = get_snapshot_user_ids(vacancy)
    assert set(snapshot_ids) == {w.id for w in workers}, (
        f"Snapshot must contain the 3 current MEMBERs, got: {snapshot_ids}"
    )
    assert (vacancy.extra or {}).get("refind_deadline"), (
        "Stage 6.A: refind_deadline must be set to start the 1-hour timer"
    )
