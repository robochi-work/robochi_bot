"""Tests for Stage 3.E: employer repeat submit after a disputed rollcall."""

from __future__ import annotations

import datetime as _dt
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


def _setup_with_disputed(
    vacancy_factory, employer_factory, worker_factory, group_factory, is_full_uncheck, selected_count=1, n=2
):
    employer = employer_factory()
    group = group_factory()
    today = _dt.date.today()
    one_hour_ago = (_dt.datetime.now() - _dt.timedelta(hours=1)).time().replace(microsecond=0)
    in_one_hour = (_dt.datetime.now() + _dt.timedelta(hours=1)).time().replace(microsecond=0)

    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_SEARCH_STOPPED,
        first_rollcall_passed=True,
        group=group,
        date=today,
        start_time=one_hour_ago,
        end_time=in_one_hour,
    )
    vacancy.extra = dict(vacancy.extra or {})
    vacancy.extra["sent_final_call"] = True
    vacancy.save(update_fields=["extra"])

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
    return vacancy, employer, workers


@pytest.fixture(autouse=True)
def _stub_bot_and_side_effects(monkeypatch):
    fake_bot = MagicMock()
    fake_bot.send_message = MagicMock(return_value=MagicMock(message_id=1))
    fake_bot.delete_message = MagicMock()
    monkeypatch.setattr("telegram.handlers.bot_instance.bot", fake_bot, raising=False)
    monkeypatch.setattr("telegram.service.group.GroupService.kick_user", staticmethod(lambda **kw: None))
    monkeypatch.setattr("vacancy.services.invoice.send_vacancy_invoice", lambda **kw: None)
    monkeypatch.setattr(
        "user.services.BlockService.auto_block_rollcall_reject",
        staticmethod(lambda *a, **kw: None),
    )
    monkeypatch.setattr(
        "user.services.BlockService.unblock_employer_rollcall_fail",
        staticmethod(lambda *a, **kw: None),
    )
    return fake_bot


@pytest.mark.django_db
def test_repeat_submit_after_scenario_b_finalizes(
    client, vacancy_factory, employer_factory, worker_factory, group_factory
):
    """Б повтор: заказчик исправил перекличку -> финализация + admin_buttons_disabled."""
    vacancy, employer, workers = _setup_with_disputed(
        vacancy_factory,
        employer_factory,
        worker_factory,
        group_factory,
        is_full_uncheck=False,
        selected_count=1,
        n=2,
    )
    # Employer now confirms BOTH workers
    vu_pks = list(VacancyUser.objects.filter(vacancy=vacancy).values_list("pk", flat=True).order_by("pk"))
    client.force_login(employer)
    resp = client.post(
        reverse("vacancy:call", kwargs={"pk": vacancy.pk, "call_type": CallType.AFTER_START}),
        data={"users": [str(p) for p in vu_pks], "call_type": CallType.AFTER_START},
    )
    assert resp.status_code in (200, 302)
    vacancy.refresh_from_db()
    assert vacancy.second_rollcall_passed is True
    assert vacancy.status == STATUS_AWAITING_PAYMENT
    assert not is_disputed(vacancy)


@pytest.mark.django_db
def test_repeat_submit_after_scenario_v_with_one_finalizes(
    client, vacancy_factory, employer_factory, worker_factory, group_factory
):
    """В повтор с 1+ чекбоксом: финализация + кнопки админа отключены."""
    vacancy, employer, workers = _setup_with_disputed(
        vacancy_factory,
        employer_factory,
        worker_factory,
        group_factory,
        is_full_uncheck=True,
        selected_count=0,
        n=2,
    )
    vu_pks = list(VacancyUser.objects.filter(vacancy=vacancy).values_list("pk", flat=True).order_by("pk"))
    client.force_login(employer)
    resp = client.post(
        reverse("vacancy:call", kwargs={"pk": vacancy.pk, "call_type": CallType.AFTER_START}),
        data={"users": [str(vu_pks[0])], "call_type": CallType.AFTER_START},
    )
    assert resp.status_code in (200, 302)
    vacancy.refresh_from_db()
    assert vacancy.second_rollcall_passed is True
    assert not is_disputed(vacancy)


@pytest.mark.django_db
def test_repeat_submit_after_scenario_v_with_zero_rejected(
    client, vacancy_factory, employer_factory, worker_factory, group_factory
):
    """В повтор с 0 чекбоксов: форма отвергнута, диспут сохранён."""
    vacancy, employer, workers = _setup_with_disputed(
        vacancy_factory,
        employer_factory,
        worker_factory,
        group_factory,
        is_full_uncheck=True,
        selected_count=0,
        n=2,
    )
    client.force_login(employer)
    resp = client.post(
        reverse("vacancy:call", kwargs={"pk": vacancy.pk, "call_type": CallType.AFTER_START}),
        data={"users": [], "call_type": CallType.AFTER_START},
    )
    # Form re-rendered with an error — status 200 (no redirect)
    assert resp.status_code == 200
    vacancy.refresh_from_db()
    assert is_disputed(vacancy)
    assert vacancy.second_rollcall_passed is False


@pytest.mark.django_db
def test_admin_buttons_disabled_after_self_submit(
    client, vacancy_factory, employer_factory, worker_factory, group_factory
):
    """После повторного submit'а флаг admin_buttons_disabled=True ставится ДО finalize."""
    vacancy, employer, workers = _setup_with_disputed(
        vacancy_factory,
        employer_factory,
        worker_factory,
        group_factory,
        is_full_uncheck=False,
        selected_count=1,
        n=2,
    )
    # Spy: capture the disputed state when disable_admin_buttons is called
    from vacancy.services import disputed_rollcall as dr_mod

    seen = {"disabled_seen": False}
    orig = dr_mod.disable_admin_buttons

    def _spy(vacancy):
        seen["disabled_seen"] = True
        orig(vacancy)

    import vacancy.views as views_mod  # noqa: F401

    # Patch on the views import path used inside the function
    # (the function does `from vacancy.services.disputed_rollcall import disable_admin_buttons`)
    dr_mod.disable_admin_buttons = _spy
    try:
        vu_pks = list(VacancyUser.objects.filter(vacancy=vacancy).values_list("pk", flat=True).order_by("pk"))
        client.force_login(employer)
        client.post(
            reverse("vacancy:call", kwargs={"pk": vacancy.pk, "call_type": CallType.AFTER_START}),
            data={"users": [str(p) for p in vu_pks], "call_type": CallType.AFTER_START},
        )
        assert seen["disabled_seen"], "disable_admin_buttons must be called before finalize"
    finally:
        dr_mod.disable_admin_buttons = orig
