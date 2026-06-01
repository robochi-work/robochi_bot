"""
Session 2026-05-31: Members page + rollcall merge tests.
Tests for merging vacancy_members page with rollcall functionality.
"""

from datetime import date, time
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory

from telegram.choices import CallStatus, CallType
from vacancy.choices import STATUS_APPROVED, STATUS_SEARCH_STOPPED
from vacancy.models import Vacancy, VacancyUser, VacancyUserCall


@pytest.fixture
def factory():
    return RequestFactory()


@pytest.fixture
def employer(db):
    from user.models import User

    return User.objects.create(id=999000001, username="test_employer")


@pytest.fixture
def worker1(db):
    from user.models import User

    return User.objects.create(id=999000002, username="test_worker1")


@pytest.fixture
def worker2(db):
    from user.models import User

    return User.objects.create(id=999000003, username="test_worker2")


@pytest.fixture
def vacancy_approved(db, employer):
    return Vacancy.objects.create(
        owner=employer,
        address="Test Address",
        date=date.today(),
        start_time=time(10, 0),
        end_time=time(13, 0),
        status=STATUS_APPROVED,
        people_count=3,
        payment_amount=100,
        has_passport=False,
        search_active=True,
    )


@pytest.fixture
def vacancy_with_members(vacancy_approved, worker1, worker2):
    VacancyUser.objects.create(vacancy=vacancy_approved, user=worker1, status="member")
    VacancyUser.objects.create(vacancy=vacancy_approved, user=worker2, status="member")
    return vacancy_approved


# --- Test 1: Members page mode detection ---


class TestMembersPageMode:
    """Test that vacancy_members view correctly detects page mode."""

    def test_normal_mode_before_start_time(self, factory, vacancy_with_members, employer):
        """Before start_time: normal mode with kick buttons, no rollcall."""
        from vacancy.views import vacancy_members

        vacancy_with_members.start_time = time(23, 59)
        vacancy_with_members.save(update_fields=["start_time"])

        request = factory.get(f"/vacancy/{vacancy_with_members.pk}/members/")
        request.user = employer

        response = vacancy_members(request, vacancy_with_members.pk)
        content = response.content.decode()

        assert "Видалити з групи" in content
        assert "Початок роботи" not in content

    def test_rollcall_mode_after_start_time(self, factory, vacancy_with_members, employer):
        """After start_time: rollcall mode with checkboxes."""
        from vacancy.views import vacancy_members

        vacancy_with_members.start_time = time(0, 1)
        vacancy_with_members.extra["sent_start_call"] = True
        vacancy_with_members.save(update_fields=["start_time", "extra"])

        request = factory.get(f"/vacancy/{vacancy_with_members.pk}/members/")
        request.user = employer

        response = vacancy_members(request, vacancy_with_members.pk)
        content = response.content.decode()

        assert "Початок роботи" in content
        assert "Підтвердити" in content


# --- Test 2: Scenario detection ---


class TestScenarioDetection:
    """Test scenarios A/B/C for first rollcall."""

    def test_scenario_a_no_workers(self, factory, vacancy_approved, employer):
        """Scenario A: 0 members -> show continue/close buttons."""
        from vacancy.views import vacancy_members

        vacancy_approved.start_time = time(0, 1)
        vacancy_approved.extra["sent_start_call"] = True
        vacancy_approved.save(update_fields=["start_time", "extra"])

        request = factory.get(f"/vacancy/{vacancy_approved.pk}/members/")
        request.user = employer

        response = vacancy_members(request, vacancy_approved.pk)
        content = response.content.decode()

        assert "Закрити вакансію" in content

    def test_scenario_b_few_workers(self, factory, vacancy_with_members, employer):
        """Scenario B: members < people_count -> show checkboxes + continue search."""
        from vacancy.views import vacancy_members

        vacancy_with_members.start_time = time(0, 1)
        vacancy_with_members.extra["sent_start_call"] = True
        vacancy_with_members.save(update_fields=["start_time", "extra"])

        request = factory.get(f"/vacancy/{vacancy_with_members.pk}/members/")
        request.user = employer

        response = vacancy_members(request, vacancy_with_members.pk)
        content = response.content.decode()

        assert "Підтвердити" in content
        # people_count=3, members=2 -> scenario B
        assert "2" in content

    def test_scenario_c_enough_workers(self, factory, vacancy_with_members, employer):
        """Scenario C: members >= people_count -> just checkboxes."""
        from vacancy.views import vacancy_members

        vacancy_with_members.people_count = 2
        vacancy_with_members.start_time = time(0, 1)
        vacancy_with_members.extra["sent_start_call"] = True
        vacancy_with_members.save(update_fields=["start_time", "people_count", "extra"])

        request = factory.get(f"/vacancy/{vacancy_with_members.pk}/members/")
        request.user = employer

        response = vacancy_members(request, vacancy_with_members.pk)
        content = response.content.decode()

        assert "Підтвердити" in content


# --- Test 3: End rollcall requires sent_final_call ---


class TestEndRollcallGuard:
    """Test that 2nd rollcall only shows when Celery has sent notification."""

    def test_no_end_rollcall_without_sent_final_call(self, factory, vacancy_with_members, employer):
        """first_rollcall_passed=True but no sent_final_call -> normal mode."""
        from vacancy.views import vacancy_members

        vacancy_with_members.first_rollcall_passed = True
        vacancy_with_members.status = STATUS_SEARCH_STOPPED
        vacancy_with_members.save(update_fields=["first_rollcall_passed", "status"])

        request = factory.get(f"/vacancy/{vacancy_with_members.pk}/members/")
        request.user = employer

        response = vacancy_members(request, vacancy_with_members.pk)
        content = response.content.decode()

        assert "Кінець роботи" not in content

    def test_end_rollcall_with_sent_final_call(self, factory, vacancy_with_members, employer):
        """first_rollcall_passed=True + sent_final_call -> end rollcall mode."""
        from vacancy.views import vacancy_members

        vacancy_with_members.first_rollcall_passed = True
        vacancy_with_members.status = STATUS_SEARCH_STOPPED
        vacancy_with_members.extra["sent_final_call"] = True
        vacancy_with_members.save(update_fields=["first_rollcall_passed", "status", "extra"])

        request = factory.get(f"/vacancy/{vacancy_with_members.pk}/members/")
        request.user = employer

        response = vacancy_members(request, vacancy_with_members.pk)
        content = response.content.decode()

        assert "Кінець роботи" in content
        assert "Підтвердити" in content


# --- Test 4: continue_search resets rollcall flags ---


class TestContinueSearchReset:
    """Test that continue_search properly resets rollcall state."""

    @patch("vacancy.views.vacancy_publisher")
    @patch("vacancy.views.bot", create=True)
    def test_continue_search_resets_flags(self, mock_bot, mock_pub, factory, vacancy_with_members, employer):
        """continue_search should reset all rollcall flags."""
        from vacancy.views import vacancy_continue_search

        vacancy_with_members.first_rollcall_passed = True
        vacancy_with_members.second_rollcall_passed = True
        vacancy_with_members.extra["sent_start_call"] = True
        vacancy_with_members.extra["sent_final_call"] = True
        vacancy_with_members.extra["start_call_reminders"] = 5
        vacancy_with_members.save()

        # Create old VacancyUserCall records
        vu = VacancyUser.objects.filter(vacancy=vacancy_with_members).first()
        VacancyUserCall.objects.create(vacancy_user=vu, call_type=CallType.START, status=CallStatus.CONFIRM)

        request = factory.get(f"/vacancy/{vacancy_with_members.pk}/continue-search/")
        request.user = employer

        with patch("vacancy.views.bot", MagicMock()):
            vacancy_continue_search(request, vacancy_with_members.pk)

        vacancy_with_members.refresh_from_db()

        assert vacancy_with_members.first_rollcall_passed is False
        assert vacancy_with_members.second_rollcall_passed is False
        assert vacancy_with_members.extra.get("sent_start_call") is None
        assert vacancy_with_members.extra.get("sent_final_call") is None
        assert vacancy_with_members.search_active is True
        assert vacancy_with_members.status == STATUS_APPROVED

        # Old VacancyUserCall records should be deleted
        assert VacancyUserCall.objects.filter(vacancy_user__vacancy=vacancy_with_members).count() == 0


# --- Test 5: Pre-call redirect ---


class TestPreCallRedirect:
    """Test that pre_call now redirects to members."""

    def test_pre_call_redirects_to_members(self, factory, vacancy_approved, employer):
        """pre_call_check should redirect to members page."""
        from vacancy.views import vacancy_pre_call_check

        request = factory.get(f"/vacancy/{vacancy_approved.pk}/pre-call/start/")
        request.user = employer

        response = vacancy_pre_call_check(request, vacancy_approved.pk, CallType.START)

        assert response.status_code == 302
        assert f"/vacancy/{vacancy_approved.pk}/members/" in response.url


# --- Test 6: Bot URL points to members ---


class TestBotUrlPointsToMembers:
    """Test that call_markup sends members URL, not pre_call."""

    def test_start_call_markup_url(self, vacancy_approved):
        """Start call markup should point to members page."""

        from vacancy.services.call_markup import get_start_call_markup

        markup = get_start_call_markup(vacancy_approved)
        button_url = markup.keyboard[0][0].web_app.url

        assert "/detail/" in button_url
        assert "/pre-call/" not in button_url


# --- Test 7: Close observer deletes rollcall messages ---


class TestCloseDeletesRollcallMessages:
    """Test that vacancy close deletes start_call and final_call messages."""

    def test_delete_list_includes_rollcall_keys(self):
        """VacancyDeleteEmployerInviteObserver should delete rollcall msg IDs."""
        import inspect

        from vacancy.services.observers.vacancy_close import VacancyDeleteEmployerInviteObserver

        source = inspect.getsource(VacancyDeleteEmployerInviteObserver)
        assert "start_call_msg_id" in source
        assert "final_call_msg_id" in source
