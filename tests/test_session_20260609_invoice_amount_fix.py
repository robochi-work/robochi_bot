"""Регрессия: сумма счёта = факт.работников × PaymentConfig.fee.

Баг 09.06.2026: в send_unpaid_reminders_task сумма считалась как
payment_amount × people_count (зарплата работнику × план), а не
get_vacancy_invoice_amount (фактические × 100).
"""

import pytest

from work.models import PaymentConfig


@pytest.mark.django_db
def test_payment_config_default_fee():
    PaymentConfig.objects.all().delete()
    assert PaymentConfig.get_fee() == 100


@pytest.mark.django_db
def test_payment_config_custom_fee():
    PaymentConfig.objects.all().delete()
    PaymentConfig.objects.create(service_fee_per_worker=150)
    assert PaymentConfig.get_fee() == 150


@pytest.mark.django_db
def test_payment_config_singleton():
    PaymentConfig.objects.all().delete()
    PaymentConfig.objects.create(service_fee_per_worker=100)
    obj = PaymentConfig(service_fee_per_worker=200)
    obj.save()
    assert PaymentConfig.objects.count() == 1
    assert PaymentConfig.get_fee() == 200


@pytest.mark.django_db
def test_invoice_amount_2_workers(vacancy_factory):
    from telegram.choices import CallType
    from vacancy.services.invoice import get_vacancy_invoice_amount

    PaymentConfig.objects.all().delete()
    PaymentConfig.objects.create(service_fee_per_worker=100)

    vacancy = vacancy_factory()
    vacancy.extra = {"calls": {CallType.AFTER_START.value: [101, 102]}}
    vacancy.save()

    assert get_vacancy_invoice_amount(vacancy) == 200


@pytest.mark.django_db
def test_invoice_amount_uses_custom_fee(vacancy_factory):
    from telegram.choices import CallType
    from vacancy.services.invoice import get_vacancy_invoice_amount

    PaymentConfig.objects.all().delete()
    PaymentConfig.objects.create(service_fee_per_worker=130)

    vacancy = vacancy_factory()
    vacancy.extra = {"calls": {CallType.AFTER_START.value: [1, 2, 3]}}
    vacancy.save()

    assert get_vacancy_invoice_amount(vacancy) == 390


@pytest.mark.django_db
def test_validate_invoice_data_passes_when_workers_exist(vacancy_factory):
    from telegram.choices import CallType
    from vacancy.services.invoice import validate_invoice_data

    vacancy = vacancy_factory()
    vacancy.extra = {"calls": {CallType.AFTER_START.value: [42]}}
    vacancy.save()

    assert validate_invoice_data(vacancy) is True
    assert "anomaly_alerted" not in (vacancy.extra or {})


@pytest.mark.django_db
def test_validate_invoice_data_fails_when_no_workers(vacancy_factory, monkeypatch):
    """Аномалия: 0 работников + awaiting_payment → False + флаг anomaly_alerted."""
    from vacancy.services.invoice import validate_invoice_data

    # мокаем admin_broadcast (на тесте бота нет)
    called = []
    monkeypatch.setattr(
        "service.broadcast_service.TelegramBroadcastService.admin_broadcast",
        lambda self, **kw: called.append(kw.get("text", "")),
    )
    monkeypatch.setattr(
        "telegram.handlers.bot_instance.bot",
        type("FakeBot", (), {"send_message": lambda *a, **k: None})(),
    )

    vacancy = vacancy_factory()
    vacancy.extra = {"calls": {"after_start": []}}
    vacancy.save()

    assert validate_invoice_data(vacancy) is False
    vacancy.refresh_from_db()
    assert vacancy.extra.get("anomaly_alerted") is True


@pytest.mark.django_db
def test_validate_invoice_data_idempotent_alert(vacancy_factory, monkeypatch):
    """Алерт шлется ровно 1 раз даже при повторных вызовах."""
    from vacancy.services.invoice import validate_invoice_data

    call_count = [0]
    monkeypatch.setattr(
        "service.broadcast_service.TelegramBroadcastService.admin_broadcast",
        lambda self, **kw: call_count.__setitem__(0, call_count[0] + 1),
    )
    monkeypatch.setattr(
        "telegram.handlers.bot_instance.bot",
        type("FakeBot", (), {"send_message": lambda *a, **k: None})(),
    )

    vacancy = vacancy_factory()
    vacancy.extra = {"calls": {"after_start": []}}
    vacancy.save()

    validate_invoice_data(vacancy)
    validate_invoice_data(vacancy)
    validate_invoice_data(vacancy)

    assert call_count[0] == 1
