"""Regression tests for unified admin notification format.

Session 2026-06-01 fix:
- Added parse_mode="HTML" to 4 observer admin_broadcast calls
  (vacancy_close x2, feedback, refind) that were missing it.
- Verified all admin messages use admin_format.py helpers
  (format_user_block, format_user_block_with_contact, format_group_link).
- Verified ADMIN_TELEGRAM_IDS fully removed — all notifications
  go through admin_broadcast (is_staff=True query).
"""

import pytest

from tests.factories import EmployerFactory, GroupFactory, VacancyFactory, WorkerFactory


@pytest.mark.django_db
class TestAdminFormatHelpers:
    """format_user_block / format_user_block_with_contact / format_group_link."""

    def test_format_user_block_contains_all_fields(self):
        from vacancy.services.admin_format import format_user_block

        user = EmployerFactory(
            username="test_employer",
            full_name="Тест Замовник",
            phone_number="+380501112233",
        )
        result = format_user_block(user)
        assert f"<code>{user.pk}</code>" in result
        assert "Тест Замовник" in result
        assert "@test_employer" in result
        assert "+380501112233" in result

    def test_format_user_block_with_contact_shows_both_phones(self):
        from vacancy.models import VacancyContactPhone
        from vacancy.services.admin_format import format_user_block_with_contact

        employer = EmployerFactory(phone_number="+380501112233")
        group = GroupFactory()
        vacancy = VacancyFactory(owner=employer, group=group, status="approved")
        VacancyContactPhone.objects.create(vacancy=vacancy, user=employer, phone="+380999998877")

        result = format_user_block_with_contact(employer, vacancy)
        assert "+380501112233" in result
        assert "+380999998877" in result
        assert "Контактний" in result

    def test_format_user_block_with_contact_hides_duplicate(self):
        from vacancy.services.admin_format import format_user_block_with_contact

        employer = EmployerFactory(phone_number="+380501112233")
        group = GroupFactory()
        vacancy = VacancyFactory(owner=employer, group=group, status="approved")
        # No VacancyContactPhone or same phone — no "Контактний" line
        result = format_user_block_with_contact(employer, vacancy)
        assert "Контактний" not in result

    def test_format_group_link_with_group(self):
        from vacancy.services.admin_format import format_group_link

        group = GroupFactory(invite_link="https://t.me/+test123")
        vacancy = VacancyFactory(group=group, status="approved")
        result = format_group_link(vacancy)
        assert "https://t.me/+test123" in result
        assert "Група" in result

    def test_format_group_link_without_group(self):
        from vacancy.services.admin_format import format_group_link

        vacancy = VacancyFactory(group=None, status="approved")
        result = format_group_link(vacancy)
        assert result == ""


@pytest.mark.django_db
class TestAdminNotificationsParseMode:
    """All observer admin_broadcast calls must include parse_mode='HTML'."""

    def test_vacancy_close_observer_passes_parse_mode(self):
        """vacancy_close observer passes parse_mode=HTML to admin_broadcast."""
        import inspect

        from vacancy.services.observers.vacancy_close import VacancyNotifyAdminsObserver

        source = inspect.getsource(VacancyNotifyAdminsObserver.update)
        assert 'parse_mode="HTML"' in source or "parse_mode='HTML'" in source

    def test_vacancy_payment_observer_passes_parse_mode(self):
        """vacancy_payment observer passes parse_mode=HTML to admin_broadcast."""
        import inspect

        from vacancy.services.observers.vacancy_close import VacancyPaymentDoesNotExistObserver

        source = inspect.getsource(VacancyPaymentDoesNotExistObserver.update)
        assert 'parse_mode="HTML"' in source or "parse_mode='HTML'" in source

    def test_feedback_observer_passes_parse_mode(self):
        """feedback observer passes parse_mode=HTML to admin_broadcast."""
        import inspect

        from vacancy.services.observers.feedback import VacancyFeedbackAdminObserver

        source = inspect.getsource(VacancyFeedbackAdminObserver.update)
        assert 'parse_mode="HTML"' in source or "parse_mode='HTML'" in source

    def test_refind_observer_passes_parse_mode(self):
        """refind observer passes parse_mode=HTML to admin_broadcast."""
        import inspect

        from vacancy.services.observers.refind_observer import VacancyRefindAdminObserver

        source = inspect.getsource(VacancyRefindAdminObserver.update)
        assert 'parse_mode="HTML"' in source or "parse_mode='HTML'" in source

    def test_call_observer_passes_parse_mode(self):
        """call observers pass parse_mode=HTML to admin_broadcast."""
        import inspect

        from vacancy.services.observers.call_observer import (
            VacancyAfterStartCallFailObserver,
            VacancyStartCallFailObserver,
        )

        for obs_cls in (VacancyStartCallFailObserver, VacancyAfterStartCallFailObserver):
            source = inspect.getsource(obs_cls.update)
            assert 'parse_mode="HTML"' in source or "parse_mode='HTML'" in source, (
                f"{obs_cls.__name__} missing parse_mode=HTML"
            )


@pytest.mark.django_db
class TestAdminFormatContent:
    """Verify message content uses unified format."""

    def test_vacancy_closed_admin_has_owner_block(self):
        from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

        employer = EmployerFactory(username="emp1", full_name="Тест")
        group = GroupFactory(invite_link="https://t.me/+grp1")
        vacancy = VacancyFactory(owner=employer, group=group, status="closed")

        text = CallVacancyTelegramTextFormatter(vacancy).vacancy_closed_admin()
        assert "🔒" in text
        assert f"<code>{employer.pk}</code>" in text
        assert "Замовник:" in text
        assert "Група:" in text

    def test_payment_no_exist_has_owner_block(self):
        from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

        employer = EmployerFactory()
        group = GroupFactory(invite_link="https://t.me/+grp2")
        vacancy = VacancyFactory(owner=employer, group=group, status="closed")

        text = CallVacancyTelegramTextFormatter(vacancy).vacancy_payment_no_exist_admin()
        assert "💰" in text
        assert f"<code>{employer.pk}</code>" in text
        assert "Замовник:" in text
        assert "Група:" in text

    def test_feedback_shows_both_users(self):
        from user.models import UserFeedback
        from vacancy.services.vacancy_formatter import VacancyTelegramTextFormatter

        employer = EmployerFactory(full_name="Автор Тест")
        worker = WorkerFactory(full_name="Працівник Тест")
        vacancy = VacancyFactory(owner=employer, status="approved")
        feedback = UserFeedback.objects.create(owner=employer, user=worker, text="Ок", rating="like")

        text = VacancyTelegramTextFormatter(vacancy).for_admin_new_feedback(feedback)
        assert "Автор:" in text
        assert "Автор Тест" in text
        assert "Працівник:" in text
        assert "Працівник Тест" in text

    def test_scenario_b_has_counts_and_owner(self):
        from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

        employer = EmployerFactory()
        group = GroupFactory(invite_link="https://t.me/+grp3")
        vacancy = VacancyFactory(owner=employer, group=group, people_count=5, status="approved")

        text = CallVacancyTelegramTextFormatter(vacancy).admin_scenario_b(confirmed=3, needed=5)
        assert "👷" in text
        assert "Потрібно: 5" in text
        assert "Підтверджено: 3" in text
        assert f"<code>{employer.pk}</code>" in text
        assert "Група:" in text

    def test_admin_chat_moderation_has_owner(self):
        from vacancy.services.vacancy_formatter import VacancyTelegramTextFormatter

        employer = EmployerFactory(username="mod_emp")
        group = GroupFactory()
        vacancy = VacancyFactory(owner=employer, group=group, status="pending")

        text = VacancyTelegramTextFormatter(vacancy).for_admin_chat()
        assert "📋" in text
        assert "Замовник:" in text
        assert "@mod_emp" in text


@pytest.mark.django_db
class TestNoAdminTelegramIds:
    """ADMIN_TELEGRAM_IDS must not be used anywhere."""

    def test_no_admin_telegram_ids_in_settings(self):
        import pathlib

        base_py = pathlib.Path("config/django/base.py").read_text()
        assert "ADMIN_TELEGRAM_IDS" not in base_py, "ADMIN_TELEGRAM_IDS should be removed from config/django/base.py"

    def test_notify_admins_new_user_uses_broadcast(self):
        """notify_admins_new_user must use admin_broadcast, not ADMIN_TELEGRAM_IDS."""
        import inspect

        from telegram.utils import notify_admins_new_user

        source = inspect.getsource(notify_admins_new_user)
        assert "ADMIN_TELEGRAM_IDS" not in source
        assert "admin_broadcast" in source
