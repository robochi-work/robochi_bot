"""Tests for Stage 5.A: debtors list + admin_mark_paid."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock

import pytest
from django.core.management import call_command
from django.urls import reverse

from user.choices import BlockReason, BlockType
from user.models import UserBlock
from vacancy.choices import STATUS_AWAITING_PAYMENT, STATUS_PAID


@pytest.fixture
def admin_factory(db, employer_factory):
    def _make():
        u = employer_factory()
        u.is_staff = True
        u.save(update_fields=["is_staff"])
        return u

    return _make


@pytest.fixture(autouse=True)
def _stub_bot(monkeypatch):
    fake = MagicMock()
    fake.send_message = MagicMock()
    monkeypatch.setattr("telegram.handlers.bot_instance.bot", fake, raising=False)
    return fake


@pytest.mark.django_db
def test_debtors_list_shows_unpaid_vacancies(
    client, vacancy_factory, employer_factory, worker_factory, group_factory, admin_factory
):
    employer = employer_factory()
    group = group_factory()
    v_unpaid = vacancy_factory(owner=employer, status=STATUS_AWAITING_PAYMENT, group=group)
    v_paid = vacancy_factory(
        owner=employer,
        status=STATUS_PAID,
        group=group_factory(),
        extra={"is_paid": True},
    )

    admin = admin_factory()
    client.force_login(admin)
    resp = client.get(reverse("work:admin_debtors"))
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert f"#{v_unpaid.pk}" in body
    # Paid vacancy must NOT appear
    assert f"#{v_paid.pk}" not in body


@pytest.mark.django_db
def test_admin_mark_paid_marks_and_unblocks(
    client, vacancy_factory, employer_factory, group_factory, admin_factory, _stub_bot
):
    employer = employer_factory()
    group = group_factory()
    vacancy = vacancy_factory(owner=employer, status=STATUS_AWAITING_PAYMENT, group=group)
    # Pre-create a UNPAID block to verify it gets lifted
    UserBlock.objects.create(
        user=employer,
        reason=BlockReason.UNPAID,
        block_type=BlockType.TEMPORARY,
        is_active=True,
    )

    admin = admin_factory()
    client.force_login(admin)
    resp = client.post(reverse("work:admin_mark_paid", kwargs={"vacancy_id": vacancy.pk}))
    assert resp.status_code in (200, 302)

    vacancy.refresh_from_db()
    assert vacancy.extra.get("is_paid") is True
    assert vacancy.status == STATUS_PAID
    # UNPAID block lifted
    assert not UserBlock.objects.filter(user=employer, reason=BlockReason.UNPAID, is_active=True).exists()
    # Bot notification sent
    _stub_bot.send_message.assert_called_once()


@pytest.mark.django_db
def test_admin_mark_paid_idempotent(client, vacancy_factory, employer_factory, group_factory, admin_factory, _stub_bot):
    """Second call on an already-paid vacancy must not break or re-notify."""
    employer = employer_factory()
    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_PAID,
        group=group_factory(),
        extra={"is_paid": True},
    )

    admin = admin_factory()
    client.force_login(admin)
    resp = client.post(reverse("work:admin_mark_paid", kwargs={"vacancy_id": vacancy.pk}))
    assert resp.status_code in (200, 302)
    _stub_bot.send_message.assert_not_called()


@pytest.mark.django_db
def test_admin_mark_paid_get_redirects(client, vacancy_factory, employer_factory, group_factory, admin_factory):
    """GET on mark-paid endpoint must NOT mark as paid (POST-only)."""
    employer = employer_factory()
    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_AWAITING_PAYMENT,
        group=group_factory(),
    )
    admin = admin_factory()
    client.force_login(admin)
    resp = client.get(reverse("work:admin_mark_paid", kwargs={"vacancy_id": vacancy.pk}))
    assert resp.status_code in (302, 405)
    vacancy.refresh_from_db()
    assert not vacancy.extra.get("is_paid")


@pytest.mark.django_db
def test_management_command_marks_paid(vacancy_factory, employer_factory, group_factory):
    employer = employer_factory()
    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_AWAITING_PAYMENT,
        group=group_factory(),
    )
    UserBlock.objects.create(
        user=employer,
        reason=BlockReason.UNPAID,
        block_type=BlockType.TEMPORARY,
        is_active=True,
    )
    out = StringIO()
    call_command("mark_vacancy_paid", str(vacancy.pk), stdout=out)
    vacancy.refresh_from_db()
    assert vacancy.extra.get("is_paid") is True
    assert vacancy.status == STATUS_PAID
    assert not UserBlock.objects.filter(user=employer, reason=BlockReason.UNPAID, is_active=True).exists()


@pytest.mark.django_db
def test_management_command_keep_block(vacancy_factory, employer_factory, group_factory):
    employer = employer_factory()
    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_AWAITING_PAYMENT,
        group=group_factory(),
    )
    UserBlock.objects.create(
        user=employer,
        reason=BlockReason.UNPAID,
        block_type=BlockType.TEMPORARY,
        is_active=True,
    )
    out = StringIO()
    call_command("mark_vacancy_paid", str(vacancy.pk), "--keep-block", stdout=out)
    vacancy.refresh_from_db()
    assert vacancy.extra.get("is_paid") is True
    assert UserBlock.objects.filter(user=employer, reason=BlockReason.UNPAID, is_active=True).exists()
