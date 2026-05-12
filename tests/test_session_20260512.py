"""Regression tests for session 2026-05-12."""

from datetime import date, time, timedelta

import pytest
from django.urls import reverse

from telegram.choices import CallStatus, CallType, Status
from vacancy.models import VacancyUser, VacancyUserCall


@pytest.mark.django_db
class TestRollcallTimeReached:
    def test_rollcall_time_reached_after_continue_search(self, client, employer_factory, vacancy_factory):
        owner = employer_factory()
        # start_time is in the future (tomorrow), so time-based check would be False
        # but sent_start_call=True overrides it
        vacancy = vacancy_factory(
            owner=owner,
            status="approved",
            first_rollcall_passed=False,
            extra={"sent_start_call": True},
            date=date.today() + timedelta(days=1),
            start_time=time(9, 0),
        )

        client.force_login(owner)
        response = client.get(reverse("vacancy:detail", kwargs={"pk": vacancy.pk}))

        assert response.status_code == 200
        assert response.context["rollcall_time_reached"] is True

    def test_rollcall_time_reached_without_sent_start_call(self, client, employer_factory, vacancy_factory):
        owner = employer_factory()
        # start_time is in the future and no sent_start_call flag → should be False
        vacancy = vacancy_factory(
            owner=owner,
            status="approved",
            first_rollcall_passed=False,
            extra={},
            date=date.today() + timedelta(days=1),
            start_time=time(9, 0),
        )

        client.force_login(owner)
        response = client.get(reverse("vacancy:detail", kwargs={"pk": vacancy.pk}))

        assert response.status_code == 200
        assert response.context["rollcall_time_reached"] is False


class TestNightShiftDateLabels:
    def test_night_shift_date_labels(self):
        from vacancy.forms import VacancyForm

        form = VacancyForm(initial={"start_time": time(23, 0), "end_time": time(4, 0)})
        all_labels = " ".join(str(label) for _, label in form.fields["date_choice"].choices)
        assert "ніч" in all_labels

    def test_day_shift_date_labels_no_night(self):
        from vacancy.forms import VacancyForm

        form = VacancyForm(initial={"start_time": time(9, 0), "end_time": time(17, 0)})
        all_labels = " ".join(str(label) for _, label in form.fields["date_choice"].choices)
        assert "ніч" not in all_labels


@pytest.mark.django_db
class TestFirstRollcallDefaultCheckboxes:
    def test_first_rollcall_default_checkboxes_all_checked(
        self, client, employer_factory, worker_factory, vacancy_factory
    ):
        owner = employer_factory()
        vacancy = vacancy_factory(owner=owner, status="approved", first_rollcall_passed=False)
        w1 = worker_factory()
        w2 = worker_factory()
        vu1 = VacancyUser.objects.create(vacancy=vacancy, user=w1, status=Status.MEMBER)
        vu2 = VacancyUser.objects.create(vacancy=vacancy, user=w2, status=Status.MEMBER)

        # No VacancyUserCall records for START exist yet
        client.force_login(owner)
        response = client.get(reverse("vacancy:call", kwargs={"pk": vacancy.pk, "call_type": "start"}))

        assert response.status_code == 200
        form = response.context["form"]
        initial_users = form.initial.get("users", [])
        assert {u.pk for u in initial_users} == {vu1.pk, vu2.pk}


@pytest.mark.django_db
class TestAdminCallFailEmployerBlock:
    def test_admin_call_fail_includes_employer_data(self, employer_factory, worker_factory, vacancy_factory):
        from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

        owner = employer_factory()
        vacancy = vacancy_factory(owner=owner, status="approved")
        w = worker_factory()
        vu = VacancyUser.objects.create(vacancy=vacancy, user=w, status=Status.MEMBER)
        VacancyUserCall.objects.create(vacancy_user=vu, call_type=CallType.START, status=CallStatus.REJECT)

        result = CallVacancyTelegramTextFormatter(vacancy=vacancy).admin_call_fail(CallType.START)

        assert "<b>ID:</b>" in result
        assert owner.full_name in result
