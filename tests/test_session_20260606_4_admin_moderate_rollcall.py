"""Tests for Stage 4: admin_moderate_rollcall view."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from django.urls import reverse

from telegram.choices import CallStatus, CallType, Status
from vacancy.choices import STATUS_AWAITING_PAYMENT, STATUS_SEARCH_STOPPED
from vacancy.models import VacancyUser, VacancyUserCall
from vacancy.services.disputed_rollcall import (
    is_disputed,
    mark_disputed,
)
from vacancy.services.rollcall_snapshot import save_first_rollcall_snapshot


def _setup_dispute(
    vacancy_factory,
    employer_factory,
    worker_factory,
    group_factory,
    admin_factory,
    *,
    is_full_uncheck,
    selected_count=1,
    n=2,
):
    employer = employer_factory()
    admin = admin_factory()
    group = group_factory()
    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_SEARCH_STOPPED,
        first_rollcall_passed=True,
        group=group,
    )
    workers = []
    for _ in range(n):
        w = worker_factory()
        vu = VacancyUser.objects.create(vacancy=vacancy, user=w, status=Status.MEMBER)
        VacancyUserCall.objects.create(vacancy_user=vu, call_type=CallType.AFTER_START, status=CallStatus.CREATED)
        workers.append(w)
    save_first_rollcall_snapshot(vacancy, [w.id for w in workers])
    sel = [w.id for w in workers[:selected_count]]
    rej = [w.id for w in workers[selected_count:]]
    mark_disputed(
        vacancy,
        first_count=n,
        selected_user_ids=sel,
        rejected_user_ids=rej,
        is_full_uncheck=is_full_uncheck,
    )
    vacancy.refresh_from_db()
    return vacancy, admin, employer, workers


@pytest.fixture
def admin_factory(db, employer_factory):
    """Create a staff user (reuses employer_factory then flips is_staff)."""

    def _make():
        u = employer_factory()
        u.is_staff = True
        u.save(update_fields=["is_staff"])
        return u

    return _make


@pytest.fixture(autouse=True)
def _stub_side_effects(monkeypatch):
    monkeypatch.setattr("vacancy.services.invoice.send_vacancy_invoice", lambda **kw: None)
    monkeypatch.setattr(
        "user.services.BlockService.auto_block_rollcall_reject",
        staticmethod(lambda *a, **kw: None),
    )
    monkeypatch.setattr(
        "user.services.BlockService.unblock_employer_rollcall_fail",
        staticmethod(lambda *a, **kw: None),
    )
    fake = MagicMock()
    monkeypatch.setattr("telegram.handlers.bot_instance.bot", fake, raising=False)


def _url(vacancy_id):
    return reverse("work:admin_moderate_rollcall", kwargs={"vacancy_id": vacancy_id, "call_type": "after_start"})


@pytest.mark.django_db
def test_get_renders_form_with_employer_selection_prefilled(
    client, vacancy_factory, employer_factory, worker_factory, group_factory, admin_factory
):
    vacancy, admin, _, workers = _setup_dispute(
        vacancy_factory,
        employer_factory,
        worker_factory,
        group_factory,
        admin_factory,
        is_full_uncheck=False,
        selected_count=1,
        n=2,
    )
    client.force_login(admin)
    resp = client.get(_url(vacancy.pk))
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert "Перевірка другої переклички" in body


@pytest.mark.django_db
def test_admin_can_add_checkbox_in_scenario_b(
    client, vacancy_factory, employer_factory, worker_factory, group_factory, admin_factory
):
    """Scenario Б: admin adds the previously unchecked worker -> finalizes with count=2."""
    vacancy, admin, _, workers = _setup_dispute(
        vacancy_factory,
        employer_factory,
        worker_factory,
        group_factory,
        admin_factory,
        is_full_uncheck=False,
        selected_count=1,
        n=2,
    )
    vu_pks = list(VacancyUser.objects.filter(vacancy=vacancy).values_list("pk", flat=True))
    client.force_login(admin)
    resp = client.post(_url(vacancy.pk), {"users": [str(p) for p in vu_pks], "call_type": "after_start"})
    assert resp.status_code in (200, 302)
    vacancy.refresh_from_db()
    assert vacancy.second_rollcall_passed is True
    assert vacancy.status == STATUS_AWAITING_PAYMENT
    assert not is_disputed(vacancy)


@pytest.mark.django_db
def test_admin_cannot_remove_checkbox_in_scenario_b(
    client, vacancy_factory, employer_factory, worker_factory, group_factory, admin_factory
):
    """Scenario Б: admin tries to uncheck a confirmed worker -> form error, no finalize."""
    vacancy, admin, _, workers = _setup_dispute(
        vacancy_factory,
        employer_factory,
        worker_factory,
        group_factory,
        admin_factory,
        is_full_uncheck=False,
        selected_count=1,
        n=2,
    )
    client.force_login(admin)
    # Send NO users — that's a "remove" of the previously selected one
    resp = client.post(_url(vacancy.pk), {"users": [], "call_type": "after_start"})
    assert resp.status_code == 200
    vacancy.refresh_from_db()
    assert is_disputed(vacancy)
    assert vacancy.second_rollcall_passed is False


@pytest.mark.django_db
def test_admin_can_set_zero_in_scenario_v(
    client, vacancy_factory, employer_factory, worker_factory, group_factory, admin_factory
):
    """Scenario В: admin can finalize with count=0 (unchecking allowed)."""
    vacancy, admin, _, workers = _setup_dispute(
        vacancy_factory,
        employer_factory,
        worker_factory,
        group_factory,
        admin_factory,
        is_full_uncheck=True,
        selected_count=0,
        n=2,
    )
    client.force_login(admin)
    resp = client.post(_url(vacancy.pk), {"users": [], "call_type": "after_start"})
    assert resp.status_code in (200, 302)
    vacancy.refresh_from_db()
    assert vacancy.second_rollcall_passed is True
    assert not is_disputed(vacancy)


@pytest.mark.django_db
def test_non_admin_blocked(client, vacancy_factory, employer_factory, worker_factory, group_factory, admin_factory):
    """Non-staff user must not access the admin moderate view."""
    vacancy, _, employer, _ = _setup_dispute(
        vacancy_factory,
        employer_factory,
        worker_factory,
        group_factory,
        admin_factory,
        is_full_uncheck=False,
        selected_count=1,
        n=2,
    )
    client.force_login(employer)  # employer is NOT staff
    resp = client.get(_url(vacancy.pk))
    assert resp.status_code in (302, 403, 404)
