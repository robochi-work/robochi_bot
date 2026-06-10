"""Регрессия: двойной POST в vacancy_create не должен создавать дубль вакансии."""

from datetime import time as _time
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from vacancy.choices import STATUS_APPROVED, STATUS_CLOSED, STATUS_PENDING
from vacancy.models import Vacancy


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_double_post_does_not_create_duplicate(client, employer_factory):
    """Две одинаковые POST подряд → создаётся максимум одна вакансия (кэш-локер)."""
    employer = employer_factory()
    client.force_login(employer)

    payload = {
        "gender": "M",
        "people_count": 2,
        "address": "Тест 1",
        "date_choice": "tomorrow",
        "start_time": "10:00",
        "end_time": "13:00",
        "payment_amount": 65,
        "payment_unit": "shift",
        "payment_method": "cash",
        "skills": "test",
        "has_passport": False,
    }
    url = reverse("vacancy:create")

    r1 = client.post(url, payload)
    r2 = client.post(url, payload)

    assert r1.status_code in (200, 302)
    assert r2.status_code in (200, 302)
    assert Vacancy.objects.filter(owner=employer).count() <= 1


@pytest.mark.django_db
def test_dedup_filter_catches_pending_and_approved(employer_factory, vacancy_factory):
    """ORM-фильтр должен ловить и PENDING, и APPROVED вакансии."""
    employer = employer_factory()
    tomorrow = (timezone.now() + timedelta(days=1)).date()

    v = vacancy_factory(
        owner=employer,
        date=tomorrow,
        start_time=_time(10, 0),
        status=STATUS_APPROVED,
    )

    recent = Vacancy.objects.filter(
        owner=employer,
        status__in=[STATUS_PENDING, STATUS_APPROVED],
        date=tomorrow,
        start_time=_time(10, 0),
    ).first()

    assert recent is not None
    assert recent.pk == v.pk


@pytest.mark.django_db
def test_dedup_filter_ignores_closed_vacancy(employer_factory, vacancy_factory):
    """Закрытая вакансия не должна блокировать создание новой."""
    employer = employer_factory()
    tomorrow = (timezone.now() + timedelta(days=1)).date()

    vacancy_factory(
        owner=employer,
        date=tomorrow,
        start_time=_time(10, 0),
        status=STATUS_CLOSED,
    )

    recent = Vacancy.objects.filter(
        owner=employer,
        status__in=[STATUS_PENDING, STATUS_APPROVED],
        date=tomorrow,
        start_time=_time(10, 0),
    ).first()

    assert recent is None
