"""Tests for session 2026-05-27 changes."""

import pytest

from vacancy.choices import STATUS_APPROVED, STATUS_AWAITING_PAYMENT, STATUS_CLOSED


@pytest.mark.django_db
class TestCloseLifecycleWithPayment:
    """When employer closes vacancy after 1st rollcall with workers — invoice instead of close."""

    def test_close_after_rollcall_with_workers_sets_awaiting(
        self, client, employer_factory, vacancy_factory, worker_factory
    ):
        employer = employer_factory()
        vacancy = vacancy_factory(owner=employer, status=STATUS_APPROVED)
        vacancy.first_rollcall_passed = True
        vacancy.save(update_fields=["first_rollcall_passed"])

        worker = worker_factory()
        from vacancy.models import VacancyUser

        VacancyUser.objects.create(vacancy=vacancy, user=worker, status="member")

        client.force_login(employer)
        client.post(f"/vacancy/{vacancy.pk}/close-lifecycle/")

        vacancy.refresh_from_db()
        assert vacancy.status == STATUS_AWAITING_PAYMENT
        assert vacancy.closed_at is None
        assert "after_start" in vacancy.extra.get("calls", {})
        assert worker.pk in vacancy.extra["calls"]["after_start"]

    def test_close_without_rollcall_sets_closed(self, client, employer_factory, vacancy_factory):
        employer = employer_factory()
        vacancy = vacancy_factory(owner=employer, status=STATUS_APPROVED)

        client.force_login(employer)
        client.post(f"/vacancy/{vacancy.pk}/close-lifecycle/")

        vacancy.refresh_from_db()
        assert vacancy.status == STATUS_CLOSED
        assert vacancy.closed_at is not None

    def test_close_after_rollcall_no_workers_sets_closed(self, client, employer_factory, vacancy_factory):
        employer = employer_factory()
        vacancy = vacancy_factory(owner=employer, status=STATUS_APPROVED)
        vacancy.first_rollcall_passed = True
        vacancy.save(update_fields=["first_rollcall_passed"])

        client.force_login(employer)
        client.post(f"/vacancy/{vacancy.pk}/close-lifecycle/")

        vacancy.refresh_from_db()
        assert vacancy.status == STATUS_CLOSED
        assert vacancy.closed_at is not None


@pytest.mark.django_db
class TestActiveVacanciesCount:
    def test_counts_stopped_vacancies(self, client, employer_factory, vacancy_factory):
        from vacancy.choices import STATUS_SEARCH_STOPPED

        employer = employer_factory()
        vacancy_factory(owner=employer, status=STATUS_SEARCH_STOPPED)

        client.force_login(employer)
        response = client.get("/")
        content = response.content.decode()
        assert "Немає активних" not in content


class TestTemplateChanges:
    def test_call_confirm_has_redirect(self):
        with open("vacancy/templates/vacancy/call_confirm.html") as f:
            content = f.read()
        assert "vacancy.pk" in content
        assert "setTimeout" in content

    def test_no_participant_label(self):
        with open("vacancy/templates/vacancy/vacancy_members.html") as f:
            content = f.read()
        assert "Участник" not in content
        assert "Рейтинг/Відгуки" in content

    def test_detail_uses_splatiti(self):
        with open("vacancy/templates/vacancy/vacancy_detail.html") as f:
            content = f.read()
        assert "Оплатити рахунок" not in content
        assert "Сплатити рахунок" in content

    def test_no_contacts_button(self):
        with open("vacancy/templates/vacancy/vacancy_user_list.html") as f:
            content = f.read()
        assert "Подивитися контакти" not in content

    def test_no_first_rollcall_link(self):
        with open("vacancy/templates/vacancy/call.html") as f:
            content = f.read()
        assert "першої переклички" not in content

    def test_awaiting_status_has_red_style(self):
        with open("vacancy/templates/vacancy/vacancy_my_list.html") as f:
            content = f.read()
        assert "status--awaiting" in content
        assert "#dc3545" in content


class TestRegressionSession20260527:
    """Regression tests for all session 2026-05-27 changes."""

    def test_call_html_has_new_design(self):
        with open("vacancy/templates/vacancy/call.html") as f:
            content = f.read()
        assert "першої переклички" not in content
        assert "Меню" not in content
        assert "page--vacancy-detail" in content
        assert "call-users-list" in content

    def test_vacancy_members_new_layout(self):
        with open("vacancy/templates/vacancy/vacancy_members.html") as f:
            content = f.read()
        assert "Участник" not in content
        assert "Рейтинг/Відгуки" in content
        assert "btn-secondary btn-block" in content

    def test_employer_dashboard_has_payment_button_in_block(self):
        with open("work/templates/work/employer_dashboard.html") as f:
            content = f.read()
        assert "Сплатити рахунок" in content
        assert "Сплатіть рахунок" in content

    def test_awaiting_status_red_in_my_list(self):
        with open("vacancy/templates/vacancy/vacancy_my_list.html") as f:
            content = f.read()
        assert "status--awaiting" in content
        assert "#dc3545" in content
        assert "status--stopped" in content
        assert "status--paid" in content

    def test_reset_group_has_recheck_admins(self):
        with open("telegram/service/group.py") as f:
            content = f.read()
        assert "Re-check admins" in content
        assert "until_date=int(time.time()) + 35" in content

    def test_before_start_check_uses_5_minutes(self):
        with open("vacancy/services/observers/call_observer.py") as f:
            content = f.read()
        assert "check_before_5_start" in content
        assert "KICK_AFTER = 300" in content
        assert "REMIND_MINUTES" in content
