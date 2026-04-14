"""
Regression tests for session 2026-04-14 changes.
Run: DJANGO_SETTINGS_MODULE=config.django.local pytest tests/test_session_20260414.py -v
"""

import datetime as d
from datetime import timedelta

import pytest
from django.utils import timezone


@pytest.fixture
def vacancy_factory(db):
    """Create a Vacancy with required relations."""
    from city.models import City
    from telegram.models import Channel, Group
    from user.models import User
    from work.models import UserWorkProfile

    city = City.objects.create(id=99)
    channel = Channel.objects.create(id=-100199, city=city, invite_link="https://t.me/test", has_bot_administrator=True)
    group = Group.objects.create(id=-100299, invite_link="https://t.me/+test", status="available", is_active=True)

    def _create(owner_id=111111, **kwargs):
        user, _ = User.objects.get_or_create(
            id=owner_id,
            defaults={"full_name": "Test Employer", "phone_number": "+380991234567"},
        )
        UserWorkProfile.objects.get_or_create(
            user=user, defaults={"role": "employer", "city": city, "is_completed": True, "agreement_accepted": True}
        )
        defaults = {
            "owner": user,
            "status": "approved",
            "gender": "m",
            "people_count": 2,
            "has_passport": False,
            "address": "Test Address",
            "date": d.date.today(),
            "date_choice": "now",
            "start_time": d.time(10, 0),
            "end_time": d.time(16, 0),
            "payment_amount": 100,
            "payment_unit": "shift",
            "payment_method": "cash",
            "skills": "Test",
            "channel": channel,
            "group": group,
        }
        defaults.update(kwargs)
        from vacancy.models import Vacancy

        return Vacancy.objects.create(**defaults)

    return _create


# === 1. Block messages ===


class TestBlockMessages:
    def test_permanent_block_text(self):
        from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

        text = CallVacancyTelegramTextFormatter.auto_block_message(reason="Постійне блокування")
        assert "robochi.work" in text
        assert "@robochi_work_admin" in text
        assert "robochi_bot" not in text

    def test_block_text_in_commands(self):
        """Verify commands.py block text contains new domain."""
        import ast

        with open("telegram/handlers/messages/commands.py") as f:
            source = f.read()
        assert "robochi.work" in source
        assert "@robochi_work_admin" in source
        # Verify it parses without SyntaxError
        ast.parse(source)

    def test_block_text_in_admin_panel(self):
        """Verify admin_panel.py block texts contain new domain."""
        import ast

        with open("work/views/admin_panel.py") as f:
            source = f.read()
        assert "robochi.work" in source
        assert "@robochi_work_admin" in source
        ast.parse(source)


# === 2. Approved observer — no duplicate message ===


class TestApprovedObserver:
    def test_no_add_employer_to_group_method(self):
        """_add_employer_to_group should be removed."""
        from vacancy.services.observers.approved_group_observer import VacancyApprovedGroupObserver

        assert not hasattr(VacancyApprovedGroupObserver, "_add_employer_to_group")

    def test_approved_user_text(self):
        from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

        text = CallVacancyTelegramTextFormatter.vacancy_approved_user()
        assert "опубліковано для пошуку робітників" in text


# === 3. Final call timing — 1 hour before end_time ===


class TestFinalCallTiming:
    def test_get_final_call_vacancies_before_end(self, vacancy_factory):
        """Vacancy should appear in final call list 1h before end_time."""
        from vacancy.tasks.call import get_final_call_vacancies

        # Create vacancy ending in 30 minutes (within 1h window)
        now = timezone.localtime(timezone.now())
        end_30min = (now + timedelta(minutes=30)).time()
        start = (now - timedelta(hours=2)).time()
        vacancy = vacancy_factory(start_time=start, end_time=end_30min)

        result = list(get_final_call_vacancies())
        assert vacancy in result

    def test_get_final_call_vacancies_not_too_early(self, vacancy_factory):
        """Vacancy ending in 2 hours should NOT appear in final call list."""
        from vacancy.tasks.call import get_final_call_vacancies

        now = timezone.localtime(timezone.now())
        end_2h = (now + timedelta(hours=2)).time()
        start = (now - timedelta(hours=1)).time()
        vacancy = vacancy_factory(start_time=start, end_time=end_2h, owner_id=222222)

        result = list(get_final_call_vacancies())
        assert vacancy not in result


# === 4. MAX_REMINDERS ===


class TestMaxReminders:
    def test_max_reminders_is_12(self):
        from vacancy.tasks.call import _MAX_REMINDERS

        assert _MAX_REMINDERS == 12


# === 5. Owner permissions — no can_restrict ===


class TestOwnerPermissions:
    def test_set_default_owner_permissions_no_restrict(self):
        """Verify source has can_restrict_members=False."""
        with open("telegram/service/group.py") as f:
            source = f.read()
        # Find the set_default_owner_permissions method
        idx = source.find("def set_default_owner_permissions")
        assert idx != -1
        block = source[idx : idx + 500]
        assert "can_restrict_members=False" in block


# === 6. Vacancy form — no inherited time ===


class TestVacancyFormTime:
    def test_no_start_end_time_in_initial(self):
        """vacancy_create should not copy start_time/end_time from last vacancy."""
        with open("vacancy/views.py") as f:
            source = f.read()
        # Find the initial dict block
        idx = source.find("if last_vacancy:")
        block = source[idx : idx + 500]
        assert '"start_time": last_vacancy.start_time' not in block
        assert '"end_time": last_vacancy.end_time' not in block


# === 7. Navigation — no history.back() for admin ===


class TestAdminNavigation:
    def test_no_history_back_in_admin_vacancy_card(self):
        with open("work/templates/work/admin_vacancy_card.html") as f:
            source = f.read()
        assert "history.back()" not in source
        assert "admin_dashboard" in source

    def test_no_history_back_in_vacancy_my_list_admin(self):
        with open("vacancy/templates/vacancy/vacancy_my_list.html") as f:
            source = f.read()
        assert "history.back()" not in source

    def test_moderate_redirects_to_admin_dashboard(self):
        with open("work/views/admin_panel.py") as f:
            source = f.read()
        # After moderation, should redirect to admin_dashboard
        idx = source.find("def admin_moderate_vacancy")
        block = source[idx : idx + 3000]
        assert 'redirect("work:admin_dashboard")' in block
        assert "my_list" not in block or "for_user" not in block


# === 8. Lifecycle.js — single instance guard ===


class TestLifecycleJS:
    def test_broadcast_channel_in_lifecycle(self):
        with open("telegram/static/js/lifecycle.js") as f:
            source = f.read()
        assert "BroadcastChannel" in source
        assert "robochi_webapp" in source
        assert "new_instance" in source

    def test_retry_reload_in_lifecycle(self):
        with open("telegram/static/js/lifecycle.js") as f:
            source = f.read()
        assert "MAX_RETRIES" in source
        assert "retryCount" in source


# === 9. Favicon ===


class TestFavicon:
    def test_favicon_in_base_html(self):
        with open("templates/base.html") as f:
            source = f.read()
        assert "favicon.ico" in source

    def test_favicon_files_exist(self):
        import os

        assert os.path.exists("telegram/static/favicon.ico")
        assert os.path.exists("telegram/static/favicon-32x32.png")
        assert os.path.exists("telegram/static/apple-touch-icon.png")
