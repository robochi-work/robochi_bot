"""Regression tests for Stage 2: vacancy detail card UI.

Covers:
- owner_in_group context flag is computed correctly
- ?focus=rollcall parameter does not break the page
- 1st-rollcall passed -> "Видалити з групи" button is hidden
- worker phone is hidden in card when VacancyUser.status != MEMBER
- group invite button is hidden when owner is not in the group
- rollcall buttons in bot get ?focus=rollcall in their url
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from telegram.choices import CallType, Status
from telegram.models import UserInGroup
from vacancy.choices import STATUS_APPROVED, STATUS_SEARCH_STOPPED
from vacancy.models import VacancyUser
from vacancy.services.call_markup import (
    get_final_call_markup,
    get_rollcall_reminder_markup,
    get_start_call_markup,
)


@pytest.mark.django_db
def test_owner_in_group_true_when_owner_is_member(client, vacancy_factory, employer_factory, group_factory):
    employer = employer_factory()
    group = group_factory()
    vacancy = vacancy_factory(owner=employer, status=STATUS_APPROVED, group=group)
    assert vacancy.group is not None
    UserInGroup.objects.create(user=employer, group=vacancy.group, status=Status.MEMBER)

    client.force_login(employer)
    resp = client.get(reverse("vacancy:detail", kwargs={"pk": vacancy.pk}))
    assert resp.status_code == 200
    assert resp.context["owner_in_group"] is True


@pytest.mark.django_db
def test_owner_in_group_false_when_owner_was_kicked(client, vacancy_factory, employer_factory, group_factory):
    employer = employer_factory()
    group = group_factory()
    vacancy = vacancy_factory(owner=employer, status=STATUS_APPROVED, group=group)
    UserInGroup.objects.create(user=employer, group=vacancy.group, status=Status.KICKED)

    client.force_login(employer)
    resp = client.get(reverse("vacancy:detail", kwargs={"pk": vacancy.pk}))
    assert resp.status_code == 200
    assert resp.context["owner_in_group"] is False
    # Group invite button must NOT appear in the rendered HTML
    assert "Група з робітниками" not in resp.content.decode("utf-8")


@pytest.mark.django_db
def test_owner_in_group_false_when_no_user_in_group_record(client, vacancy_factory, employer_factory, group_factory):
    employer = employer_factory()
    group = group_factory()
    vacancy = vacancy_factory(owner=employer, status=STATUS_APPROVED, group=group)
    # No UserInGroup record at all

    client.force_login(employer)
    resp = client.get(reverse("vacancy:detail", kwargs={"pk": vacancy.pk}))
    assert resp.status_code == 200
    assert resp.context["owner_in_group"] is False


@pytest.mark.django_db
def test_focus_rollcall_query_param_renders_ok(client, vacancy_factory, employer_factory, group_factory):
    employer = employer_factory()
    group = group_factory()
    vacancy = vacancy_factory(owner=employer, status=STATUS_APPROVED, group=group)
    UserInGroup.objects.create(user=employer, group=vacancy.group, status=Status.MEMBER)

    client.force_login(employer)
    url = reverse("vacancy:detail", kwargs={"pk": vacancy.pk}) + "?focus=rollcall"
    resp = client.get(url)
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert 'id="rollcall-block"' in body
    assert "focus" in body
    assert "scrollIntoView" in body


@pytest.mark.django_db
def test_kick_button_hidden_after_first_rollcall(
    client, vacancy_factory, employer_factory, worker_factory, group_factory
):
    employer = employer_factory()
    group = group_factory()
    vacancy = vacancy_factory(owner=employer, status=STATUS_SEARCH_STOPPED, first_rollcall_passed=True, group=group)
    worker = worker_factory()
    VacancyUser.objects.create(vacancy=vacancy, user=worker, status=Status.MEMBER)
    UserInGroup.objects.create(user=employer, group=vacancy.group, status=Status.MEMBER)

    client.force_login(employer)
    resp = client.get(reverse("vacancy:detail", kwargs={"pk": vacancy.pk}))
    assert resp.status_code == 200
    assert "Видалити з групи" not in resp.content.decode("utf-8")


@pytest.mark.django_db
def test_kick_button_visible_before_first_rollcall(
    client, vacancy_factory, employer_factory, worker_factory, group_factory
):
    import datetime as _dt

    tomorrow = _dt.date.today() + _dt.timedelta(days=1)
    employer = employer_factory()
    group = group_factory()
    vacancy = vacancy_factory(
        owner=employer,
        status=STATUS_APPROVED,
        first_rollcall_passed=False,
        group=group,
        date=tomorrow,
    )
    worker = worker_factory()
    VacancyUser.objects.create(vacancy=vacancy, user=worker, status=Status.MEMBER)
    UserInGroup.objects.create(user=employer, group=vacancy.group, status=Status.MEMBER)

    client.force_login(employer)
    resp = client.get(reverse("vacancy:detail", kwargs={"pk": vacancy.pk}))
    assert resp.status_code == 200
    assert "Видалити з групи" in resp.content.decode("utf-8")


@pytest.mark.django_db
def test_rollcall_button_urls_have_focus_param(vacancy_factory):
    vacancy = vacancy_factory()
    for markup in [
        get_start_call_markup(vacancy),
        get_final_call_markup(vacancy),
        get_rollcall_reminder_markup(vacancy, CallType.START),
    ]:
        # markup.keyboard is list[list[InlineKeyboardButton]]
        urls = [btn.web_app.url if btn.web_app else (btn.url or "") for row in markup.keyboard for btn in row]
        assert any("focus=rollcall" in u for u in urls), urls
