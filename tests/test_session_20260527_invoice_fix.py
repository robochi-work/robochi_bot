"""Tests for invoice bug fix and admin mark-as-paid."""

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase

from telegram.choices import CallType
from vacancy.choices import STATUS_AWAITING_PAYMENT, STATUS_PAID


def _add_messages_support(request):
    """Add session and messages support to RequestFactory request."""
    request.session = SessionStore()
    messages = FallbackStorage(request)
    request._messages = messages
    return request


@pytest.mark.django_db
class TestAutoConfirmWritesExtraCalls(TestCase):
    """Bug fix: _escalate_rollcall must write extra['calls'] for invoice."""

    def test_escalate_second_rollcall_writes_after_start_calls(self):
        """5.F: auto-confirm now lives in auto_confirm_ignored_rollcall_task (3h after end)."""
        import datetime as _dt

        from django.utils import timezone

        from tests.factories import UserFactory, VacancyFactory
        from vacancy.choices import STATUS_SEARCH_STOPPED
        from vacancy.models import VacancyUser
        from vacancy.services.rollcall_snapshot import save_first_rollcall_snapshot

        owner = UserFactory(phone_number="+380991111111")
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

        worker = UserFactory(phone_number="+380992222222")
        VacancyUser.objects.create(vacancy=vacancy, user=worker, status="member")
        save_first_rollcall_snapshot(vacancy, [worker.id])

        with (
            patch("telegram.handlers.bot_instance.bot", MagicMock()),
            patch("vacancy.services.invoice.send_vacancy_invoice"),
        ):
            from vacancy.tasks.call import auto_confirm_ignored_rollcall_task

            auto_confirm_ignored_rollcall_task()

        vacancy.refresh_from_db()
        assert vacancy.second_rollcall_passed is True
        calls_data = vacancy.extra.get("calls", {})
        after_start = calls_data.get(CallType.AFTER_START) or calls_data.get("after_start", [])
        assert len(after_start) == 1, f"Expected 1 worker, got {after_start}"
        assert worker.id in after_start

    def test_escalate_first_rollcall_writes_start_calls(self):
        from tests.factories import UserFactory, VacancyFactory

        owner = UserFactory(phone_number="+380993333333")
        vacancy = VacancyFactory(owner=owner, has_passport=False, skills="")
        vacancy.extra = {"sent_start_call": True}
        vacancy.save()

        from vacancy.models import VacancyUser

        worker = UserFactory(phone_number="+380994444444")
        VacancyUser.objects.create(vacancy=vacancy, user=worker, status="member")

        with (
            patch("vacancy.tasks.call.GroupService"),
            patch("service.broadcast_service.TelegramBroadcastService"),
            patch("vacancy.tasks.call.telegram_notifier"),
            patch("telegram.handlers.bot_instance.bot", MagicMock()),
            patch("telegram.handlers.bot_instance.get_bot", return_value=MagicMock()),
        ):
            from vacancy.tasks.call import _escalate_rollcall

            _escalate_rollcall(vacancy, call_label="1 переклички")

        vacancy.refresh_from_db()
        assert vacancy.first_rollcall_passed is True
        calls_data = vacancy.extra.get("calls", {})
        start = calls_data.get(CallType.START) or calls_data.get("start", [])
        assert len(start) == 1, f"Expected 1 worker, got {start}"


@pytest.mark.django_db
class TestAdminMarkAsPaid(TestCase):
    """Admin action: mark vacancy as paid and unblock employer."""

    def test_mark_as_paid_changes_status_and_unblocks(self):
        from tests.factories import UserFactory, VacancyFactory
        from user.models import UserBlock
        from user.services import BlockService

        owner = UserFactory(phone_number="+380995555555")
        vacancy = VacancyFactory(owner=owner, has_passport=False, skills="")
        vacancy.status = STATUS_AWAITING_PAYMENT
        vacancy.extra["is_paid"] = False
        vacancy.save()

        BlockService.auto_block_employer_unpaid(owner)
        assert UserBlock.objects.filter(user=owner, is_active=True, reason="unpaid").exists()

        from django.contrib.admin.sites import AdminSite

        from vacancy.admin import VacancyAdmin
        from vacancy.models import Vacancy

        admin_user = UserFactory(phone_number="+380996666666")
        admin_user.is_staff = True
        admin_user.save()

        factory = RequestFactory()
        request = factory.post("/")
        request.user = admin_user
        _add_messages_support(request)

        ma = VacancyAdmin(Vacancy, AdminSite())
        with patch("telegram.handlers.bot_instance.get_bot", return_value=MagicMock()):
            ma.mark_as_paid_action(request, Vacancy.objects.filter(pk=vacancy.pk))

        vacancy.refresh_from_db()
        assert vacancy.status == STATUS_PAID
        assert vacancy.extra["is_paid"] is True
        assert vacancy.extra["admin_marked_paid"] is True
        assert not UserBlock.objects.filter(user=owner, is_active=True, reason="unpaid").exists()


@pytest.mark.django_db
class TestUnblockEmployerMarksPaid(TestCase):
    """LK Admin: unblock employer with unpaid block marks vacancies paid."""

    def test_unblock_unpaid_employer_marks_vacancy_paid(self):
        from tests.factories import UserFactory, VacancyFactory
        from user.services import BlockService

        owner = UserFactory(phone_number="+380997777777")
        vacancy = VacancyFactory(owner=owner, has_passport=False, skills="")
        vacancy.status = STATUS_AWAITING_PAYMENT
        vacancy.extra["is_paid"] = False
        vacancy.save()

        BlockService.auto_block_employer_unpaid(owner)

        admin_user = UserFactory(phone_number="+380998888888")
        admin_user.is_staff = True
        admin_user.save()

        factory = RequestFactory()
        request = factory.post("/", {"action": "unblock"})
        request.user = admin_user
        request.META["HTTP_REFERER"] = "/work/admin/"

        with patch("telegram.handlers.bot_instance.get_bot", return_value=MagicMock()):
            from work.views.admin_panel import admin_block_user

            admin_block_user(request, owner.id)

        vacancy.refresh_from_db()
        assert vacancy.status == STATUS_PAID
        assert vacancy.extra["is_paid"] is True
