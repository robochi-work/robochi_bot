"""Stage 6.B: tests for 'continue offer' DM + search_more button + scenario В block."""

from datetime import time as _time
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.utils import timezone


@pytest.fixture
def _stub_bot(monkeypatch):
    """Stub the Telegram bot — all send/delete methods become no-op mocks."""
    fake_bot = MagicMock()
    fake_sent = MagicMock()
    fake_sent.message_id = 99999
    fake_bot.send_message.return_value = fake_sent
    monkeypatch.setattr("telegram.handlers.bot_instance.bot", fake_bot)
    return fake_bot


@pytest.fixture
def _stub_celery(monkeypatch):
    """Stub finalize_continue_after_rollcall_task and delete_continue_offer_task."""
    fake_finalize = MagicMock()
    fake_delete = MagicMock()
    monkeypatch.setattr(
        "vacancy.tasks.call.finalize_continue_after_rollcall_task.apply_async",
        fake_finalize,
    )
    monkeypatch.setattr(
        "vacancy.tasks.call.delete_continue_offer_task.apply_async",
        fake_delete,
    )
    return {"finalize": fake_finalize, "delete": fake_delete}


@pytest.fixture
def _stub_broadcast(monkeypatch):
    """Stub admin_broadcast and publisher.notify so they don't try real network."""
    monkeypatch.setattr(
        "service.broadcast_service.TelegramBroadcastService.admin_broadcast",
        MagicMock(),
    )


@pytest.mark.django_db
def test_dm_offer_sent_when_partial_confirm_without_button(
    _stub_bot, _stub_celery, _stub_broadcast, employer_factory, vacancy_factory, worker_factory
):
    """Сценарий Б: 1 из 2 подтверждён, search_more НЕ нажат → DM отправлен."""
    from vacancy.services.continue_offer import send_continue_offer_dm

    employer = employer_factory()
    tomorrow = (timezone.now() + timedelta(days=1)).date()
    v = vacancy_factory(
        owner=employer,
        date=tomorrow,
        start_time=_time(10, 0),
        end_time=_time(13, 0),
        people_count=2,
        status="approved",
    )
    v.extra = {"calls": {"start": [12345]}}
    v.save(update_fields=["extra"])

    send_continue_offer_dm(v)

    _stub_bot.send_message.assert_called_once()
    args, kwargs = _stub_bot.send_message.call_args
    assert kwargs["chat_id"] == employer.id
    assert "1 з 2" in kwargs["text"]
    assert "Шукати ще" in kwargs["text"]

    v.refresh_from_db()
    assert v.extra.get("continue_offer_msg_id") == 99999
    _stub_celery["delete"].assert_called_once()


@pytest.mark.django_db
def test_dm_offer_deleted_idempotent(_stub_bot, _stub_celery, _stub_broadcast, employer_factory, vacancy_factory):
    """delete_continue_offer_msg удаляет DM и снимает флаг; повторный вызов — noop."""
    from vacancy.services.continue_offer import delete_continue_offer_msg

    employer = employer_factory()
    tomorrow = (timezone.now() + timedelta(days=1)).date()
    v = vacancy_factory(
        owner=employer,
        date=tomorrow,
        start_time=_time(10, 0),
        end_time=_time(13, 0),
        people_count=2,
        status="approved",
    )
    v.extra = {"continue_offer_msg_id": 99999}
    v.save(update_fields=["extra"])

    delete_continue_offer_msg(v)
    _stub_bot.delete_message.assert_called_once()
    v.refresh_from_db()
    assert "continue_offer_msg_id" not in (v.extra or {})

    # Повтор — должен быть no-op (не падать)
    delete_continue_offer_msg(v)
    assert _stub_bot.delete_message.call_count == 1


@pytest.mark.django_db
def test_deadline_check_inside_window(employer_factory, vacancy_factory):
    """is_within_continue_deadline: True если now < shift_start + 1ч."""
    from vacancy.services.continue_offer import is_within_continue_deadline

    employer = employer_factory()
    # Смена начинается через 30 минут — в окне
    future_start = timezone.localtime() + timedelta(minutes=30)
    v = vacancy_factory(
        owner=employer,
        date=future_start.date(),
        start_time=future_start.time().replace(microsecond=0),
        end_time=_time(23, 0),
        people_count=2,
        status="approved",
    )
    assert is_within_continue_deadline(v) is True


@pytest.mark.django_db
def test_deadline_check_outside_window(employer_factory, vacancy_factory):
    """is_within_continue_deadline: False если now >= shift_start + 1ч."""
    from vacancy.services.continue_offer import is_within_continue_deadline

    employer = employer_factory()
    past_start = timezone.localtime() - timedelta(hours=2)
    v = vacancy_factory(
        owner=employer,
        date=past_start.date(),
        start_time=past_start.time().replace(microsecond=0),
        end_time=_time(23, 0),
        people_count=2,
        status="approved",
    )
    assert is_within_continue_deadline(v) is False


@pytest.mark.django_db
def test_start_continue_search_sets_extra_and_schedules_task(
    _stub_bot, _stub_celery, _stub_broadcast, employer_factory, vacancy_factory
):
    """start_continue_search: ставит флаги в extra и планирует finalize-задачу."""
    from vacancy.services.continue_offer import start_continue_search

    employer = employer_factory()
    tomorrow = (timezone.now() + timedelta(days=1)).date()
    v = vacancy_factory(
        owner=employer,
        date=tomorrow,
        start_time=_time(10, 0),
        end_time=_time(13, 0),
        people_count=2,
        status="approved",
    )

    start_continue_search(v)
    v.refresh_from_db()

    assert v.extra.get("continue_after_first_rollcall") is True
    assert v.extra.get("continue_started_at")
    assert v.extra.get("continue_deadline")
    assert v.first_rollcall_passed is True
    assert v.status == "approved"
    assert v.search_active is True
    _stub_celery["finalize"].assert_called_once()
    args, kwargs = _stub_celery["finalize"].call_args
    assert kwargs.get("countdown") == 3600
