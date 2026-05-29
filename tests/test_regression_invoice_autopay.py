"""Regression tests: invoice after auto-confirm + admin mark-as-paid."""

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase

from telegram.choices import CallType
from vacancy.choices import STATUS_AWAITING_PAYMENT, STATUS_PAID


def _request_with_messages(method="post", data=None):
    factory = RequestFactory()
    if method == "post":
        request = factory.post("/", data or {})
    else:
        request = factory.get("/")
    request.session = SessionStore()
    request._messages = FallbackStorage(request)
    return request


@pytest.mark.django_db
class TestRegressionInvoiceAfterAutoConfirm(TestCase):
    def _create_vacancy_with_worker(self):
        from tests.factories import UserFactory, VacancyFactory
        from vacancy.models import VacancyUser

        owner = UserFactory(phone_number="+380501110001")
        worker = UserFactory(phone_number="+380501110002")
        vacancy = VacancyFactory(owner=owner, has_passport=False, skills="")
        vacancy.extra = {"sent_final_call": True}
        vacancy.first_rollcall_passed = True
        vacancy.save()
        VacancyUser.objects.create(vacancy=vacancy, user=worker, status="member")
        return vacancy, owner, worker

    def test_invoice_workers_count_after_auto_confirm(self):
        vacancy, owner, worker = self._create_vacancy_with_worker()
        with (
            patch("vacancy.tasks.call.GroupService"),
            patch("service.broadcast_service.TelegramBroadcastService"),
            patch("vacancy.tasks.call.telegram_notifier"),
            patch("telegram.handlers.bot_instance.bot", MagicMock()),
            patch("telegram.handlers.bot_instance.get_bot", return_value=MagicMock()),
            patch("vacancy.services.invoice.send_vacancy_invoice"),
        ):
            from vacancy.tasks.call import _escalate_rollcall

            _escalate_rollcall(vacancy, call_label="2 переклички")
        vacancy.refresh_from_db()
        calls = vacancy.extra.get("calls", {})
        after_start = calls.get(CallType.AFTER_START) or calls.get("after_start", [])
        assert len(after_start) > 0, "REGRESSION: extra calls after_start is empty"
        assert worker.id in after_start

    def test_invoice_amount_from_extra_calls(self):
        from tests.factories import UserFactory, VacancyFactory
        from vacancy.services.invoice import get_vacancy_invoice_amount

        owner = UserFactory(phone_number="+380501110003")
        vacancy = VacancyFactory(owner=owner, has_passport=False, skills="")
        vacancy.extra = {"calls": {"after_start": [111, 222, 333]}}
        vacancy.save()
        amount = get_vacancy_invoice_amount(vacancy, price_per_worker=100)
        assert amount == 300, f"REGRESSION: invoice amount should be 300, got {amount}"


@pytest.mark.django_db
class TestRegressionAdminMarkAsPaid(TestCase):
    def _create_unpaid_vacancy(self):
        from tests.factories import UserFactory, VacancyFactory
        from user.services import BlockService

        owner = UserFactory(phone_number="+380501110004")
        vacancy = VacancyFactory(owner=owner, has_passport=False, skills="")
        vacancy.status = STATUS_AWAITING_PAYMENT
        vacancy.extra["is_paid"] = False
        vacancy.save()
        BlockService.auto_block_employer_unpaid(owner)
        return vacancy, owner

    def test_shared_function_marks_paid_and_unblocks(self):
        from tests.factories import UserFactory
        from user.models import UserBlock
        from user.services import admin_mark_vacancies_paid

        vacancy, owner = self._create_unpaid_vacancy()
        admin_user = UserFactory(phone_number="+380501110005")
        with patch("telegram.handlers.bot_instance.get_bot", return_value=MagicMock()):
            count = admin_mark_vacancies_paid(user=owner, admin_user=admin_user)
        assert count == 1
        vacancy.refresh_from_db()
        assert vacancy.status == STATUS_PAID
        assert vacancy.extra["is_paid"] is True
        assert not UserBlock.objects.filter(user=owner, is_active=True, reason="unpaid").exists()

    def test_lk_unblock_triggers_mark_paid(self):
        from tests.factories import UserFactory

        vacancy, owner = self._create_unpaid_vacancy()
        admin_user = UserFactory(phone_number="+380501110006")
        admin_user.is_staff = True
        admin_user.save()
        request = _request_with_messages(data={"action": "unblock"})
        request.user = admin_user
        request.META["HTTP_REFERER"] = "/work/admin/"
        with patch("telegram.handlers.bot_instance.get_bot", return_value=MagicMock()):
            from work.views.admin_panel import admin_block_user

            admin_block_user(request, owner.id)
        vacancy.refresh_from_db()
        assert vacancy.status == STATUS_PAID
        assert vacancy.extra["is_paid"] is True

    def test_django_admin_action_marks_paid(self):
        from django.contrib.admin.sites import AdminSite

        from tests.factories import UserFactory
        from user.models import UserBlock
        from vacancy.admin import VacancyAdmin
        from vacancy.models import Vacancy

        vacancy, owner = self._create_unpaid_vacancy()
        admin_user = UserFactory(phone_number="+380501110007")
        admin_user.is_staff = True
        admin_user.save()
        request = _request_with_messages()
        request.user = admin_user
        ma = VacancyAdmin(Vacancy, AdminSite())
        with patch("telegram.handlers.bot_instance.get_bot", return_value=MagicMock()):
            ma.mark_as_paid_action(request, Vacancy.objects.filter(pk=vacancy.pk))
        vacancy.refresh_from_db()
        assert vacancy.status == STATUS_PAID
        assert vacancy.extra["admin_marked_paid"] is True
        assert not UserBlock.objects.filter(user=owner, is_active=True, reason="unpaid").exists()

    def test_both_paths_produce_identical_results(self):
        from tests.factories import UserFactory, VacancyFactory
        from user.services import BlockService

        owner1 = UserFactory(phone_number="+380501110008")
        v1 = VacancyFactory(owner=owner1, has_passport=False, skills="")
        v1.status = STATUS_AWAITING_PAYMENT
        v1.extra["is_paid"] = False
        v1.save()
        BlockService.auto_block_employer_unpaid(owner1)
        admin_user = UserFactory(phone_number="+380501110010")
        admin_user.is_staff = True
        admin_user.save()
        request = _request_with_messages(data={"action": "unblock"})
        request.user = admin_user
        request.META["HTTP_REFERER"] = "/work/admin/"
        with patch("telegram.handlers.bot_instance.get_bot", return_value=MagicMock()):
            from work.views.admin_panel import admin_block_user

            admin_block_user(request, owner1.id)
        v1.refresh_from_db()
        owner2 = UserFactory(phone_number="+380501110009")
        v2 = VacancyFactory(owner=owner2, has_passport=False, skills="")
        v2.status = STATUS_AWAITING_PAYMENT
        v2.extra["is_paid"] = False
        v2.save()
        BlockService.auto_block_employer_unpaid(owner2)
        from django.contrib.admin.sites import AdminSite

        from vacancy.admin import VacancyAdmin
        from vacancy.models import Vacancy

        request2 = _request_with_messages()
        request2.user = admin_user
        ma = VacancyAdmin(Vacancy, AdminSite())
        with patch("telegram.handlers.bot_instance.get_bot", return_value=MagicMock()):
            ma.mark_as_paid_action(request2, Vacancy.objects.filter(pk=v2.pk))
        v2.refresh_from_db()
        assert v1.status == v2.status == STATUS_PAID
        assert v1.extra["is_paid"] == v2.extra["is_paid"] is True
        assert v1.extra["admin_marked_paid"] == v2.extra["admin_marked_paid"] is True
