"""Regression: vacancies must not get stuck in stopped/paid status."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase
from django.utils import timezone

from vacancy.choices import STATUS_AWAITING_PAYMENT, STATUS_PAID


@pytest.mark.django_db
class TestRegressionEscalateIssuesInvoice(TestCase):
    """After auto-confirm of 2nd rollcall, invoice must be issued."""

    def test_auto_confirm_2nd_rollcall_changes_status_to_awaiting(self):
        """5.F: auto-confirm now lives in auto_confirm_ignored_rollcall_task (3h after end)."""
        import datetime as _dt

        from django.utils import timezone

        from tests.factories import UserFactory, VacancyFactory
        from vacancy.choices import STATUS_SEARCH_STOPPED
        from vacancy.models import VacancyUser
        from vacancy.services.rollcall_snapshot import save_first_rollcall_snapshot

        owner = UserFactory(phone_number="+380601110001")
        tz = timezone.get_current_timezone()
        now = timezone.now()
        end_local = (now - _dt.timedelta(hours=4)).astimezone(tz)
        start_local = end_local - _dt.timedelta(hours=8)
        vacancy = VacancyFactory(
            owner=owner,
            has_passport=False,
            skills="",
            status=STATUS_SEARCH_STOPPED,
            first_rollcall_passed=True,
            date=start_local.date(),
            start_time=start_local.time().replace(microsecond=0),
            end_time=end_local.time().replace(microsecond=0),
        )

        worker = UserFactory(phone_number="+380601110002")
        VacancyUser.objects.create(vacancy=vacancy, user=worker, status="member")
        save_first_rollcall_snapshot(vacancy, [worker.id])

        with (
            patch("telegram.handlers.bot_instance.bot", MagicMock()),
            patch("vacancy.services.invoice.send_vacancy_invoice") as mock_invoice,
        ):
            from vacancy.tasks.call import auto_confirm_ignored_rollcall_task

            auto_confirm_ignored_rollcall_task()

        vacancy.refresh_from_db()
        assert vacancy.status == STATUS_AWAITING_PAYMENT, (
            f"REGRESSION: after auto-confirm 2nd rollcall status should be awaiting, got {vacancy.status}"
        )
        mock_invoice.assert_called_once()


@pytest.mark.django_db
class TestRegressionAdminPaidGroupRelease(TestCase):
    """Admin-paid vacancies must be released by close_lifecycle_timer_task."""

    def test_timer_finds_admin_paid_vacancy(self):
        from telegram.models import Group
        from tests.factories import UserFactory, VacancyFactory

        owner = UserFactory(phone_number="+380601110003")
        group = Group.objects.create(id=-100999999, title="Test Group", invite_link="https://t.me/+test")
        vacancy = VacancyFactory(owner=owner, has_passport=False, skills="")
        vacancy.status = STATUS_PAID
        vacancy.group = group
        vacancy.search_stopped_at = timezone.now() - timedelta(hours=4)
        vacancy.extra["admin_marked_paid"] = True
        vacancy.extra["is_paid"] = True
        vacancy.save()

        with (
            patch("vacancy.tasks.call.vacancy_publisher") as mock_pub,
            patch("vacancy.tasks.call.connection"),
        ):
            from vacancy.tasks.call import close_lifecycle_timer_task

            close_lifecycle_timer_task()

        assert mock_pub.notify.called, (
            "REGRESSION: close_lifecycle_timer_task did not call VACANCY_CLOSE for admin-paid vacancy"
        )


@pytest.mark.django_db
class TestRegressionPaymentButtonHidden(TestCase):
    """Payment button must not show when vacancy is already paid."""

    def test_show_payment_false_when_status_paid(self):
        from django.test import RequestFactory

        from tests.factories import UserFactory, VacancyFactory
        from vacancy.views import vacancy_detail

        owner = UserFactory(phone_number="+380601110004")
        vacancy = VacancyFactory(owner=owner, has_passport=False, skills="")
        vacancy.status = STATUS_PAID
        vacancy.second_rollcall_passed = True
        vacancy.save()

        factory = RequestFactory()
        request = factory.get(f"/vacancy/{vacancy.pk}/")
        request.user = owner

        with patch("telegram.handlers.bot_instance.get_bot", return_value=MagicMock()):
            response = vacancy_detail(request, vacancy.pk)

        content = response.content.decode()
        assert "Сплатити рахунок" not in content, "REGRESSION: payment button visible on paid vacancy"
