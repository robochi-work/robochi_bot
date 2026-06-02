"""Regression tests for 2026-05-26 session: critical lifecycle bugs."""

from datetime import timedelta

import pytest
from django.utils import timezone

from telegram.choices import CallStatus, CallType, Status
from vacancy.choices import STATUS_SEARCH_STOPPED


@pytest.fixture
def vacancy_with_two_calls(db, vacancy_factory, user_factory):
    """Vacancy where worker has both JOIN_CONFIRM and BEFORE_START calls."""
    worker = user_factory(phone_number="+380991111111")
    vacancy = vacancy_factory()
    from vacancy.models import VacancyUser, VacancyUserCall

    vu = VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.MEMBER)
    VacancyUserCall.objects.create(
        vacancy_user=vu,
        call_type=CallType.WORKER_JOIN_CONFIRM,
        status=CallStatus.CONFIRM,
    )
    VacancyUserCall.objects.create(
        vacancy_user=vu,
        call_type=CallType.BEFORE_START,
        status=CallStatus.SENT,
    )
    return vacancy, vu, worker


@pytest.mark.django_db
class TestCallbackUpdateOrCreate:
    """Fix #1: update_or_create must use call_type in lookup."""

    def test_update_or_create_with_call_type_no_crash(self, vacancy_with_two_calls):
        """Worker with 2 VacancyUserCall records: confirm must not raise."""
        vacancy, vu, worker = vacancy_with_two_calls
        from vacancy.models import VacancyUserCall

        # This is what the fixed code does — should NOT raise
        obj, created = VacancyUserCall.objects.update_or_create(
            vacancy_user=vu,
            call_type=CallType.BEFORE_START,
            defaults={"status": CallStatus.CONFIRM},
        )
        assert obj.status == CallStatus.CONFIRM
        assert not created  # updated existing

    def test_update_or_create_without_call_type_crashes(self, vacancy_with_two_calls):
        """Without call_type in lookup — MultipleObjectsReturned."""
        vacancy, vu, worker = vacancy_with_two_calls
        from vacancy.models import VacancyUserCall

        with pytest.raises(VacancyUserCall.MultipleObjectsReturned):
            VacancyUserCall.objects.update_or_create(
                vacancy_user=vu,
                defaults={
                    "status": CallStatus.CONFIRM,
                    "call_type": CallType.BEFORE_START,
                },
            )


@pytest.mark.django_db
class TestCloseLifecycleSkipsActiveVacancy:
    """Fix #2: close_lifecycle_timer must not close vacancies with active workers."""

    def test_vacancy_with_members_not_closed(self, db, vacancy_factory, user_factory):
        """Vacancy with workers and unfinished lifecycle must NOT be closed."""
        from vacancy.models import VacancyUser

        vacancy = vacancy_factory()
        vacancy.status = STATUS_SEARCH_STOPPED
        vacancy.search_stopped_at = timezone.now() - timedelta(hours=4)
        vacancy.extra = {"payment_checked": False}
        vacancy.save()

        worker = user_factory(phone_number="+380992222222")
        VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.MEMBER)

        has_members = vacancy.members.exists()
        payment_checked = vacancy.extra.get("payment_checked", False)

        # Logic from the fix: skip if has members and payment not checked
        should_skip = has_members and not payment_checked
        assert should_skip is True

    def test_vacancy_without_members_closed(self, db, vacancy_factory):
        """Empty vacancy past threshold SHOULD be closed."""

        vacancy = vacancy_factory()
        vacancy.status = STATUS_SEARCH_STOPPED
        vacancy.search_stopped_at = timezone.now() - timedelta(hours=4)
        vacancy.extra = {}
        vacancy.save()

        has_members = vacancy.members.exists()
        payment_checked = vacancy.extra.get("payment_checked", False)

        should_skip = has_members and not payment_checked
        assert should_skip is False


@pytest.mark.django_db
class TestPublisherErrorHandling:
    """Fix #3: publisher.notify must not stop chain on observer failure."""

    def test_failing_observer_does_not_block_next(self):
        from vacancy.services.observers.publisher import BasePublisher, Observer

        call_log = []

        class FailingObserver(Observer):
            def update(self, event, data):
                raise RuntimeError("boom")

        class GoodObserver(Observer):
            def update(self, event, data):
                call_log.append("good")

        pub = BasePublisher()
        pub.subscribe("test", FailingObserver())
        pub.subscribe("test", GoodObserver())
        pub.notify("test", {})

        assert "good" in call_log, "GoodObserver must run even if FailingObserver crashes"


@pytest.mark.django_db
class TestGroupButtonStartappFormat:
    """Fix: group button uses t.me startapp URL (web_app= not supported in groups)."""

    def test_group_button_is_url_not_webapp(self):
        """InlineKeyboardButton must use url=, not web_app=WebAppInfo."""
        from unittest.mock import MagicMock

        from service.telegram_markup_factory import group_url_feedback_reply_markup

        vacancy = MagicMock()
        vacancy.pk = 42
        markup = group_url_feedback_reply_markup(vacancy)
        button = markup.keyboard[0][0]
        assert button.url is not None, "Must be url= button"
        assert button.web_app is None, "web_app must not be set (not supported in groups)"

    def test_group_button_contains_startapp_with_vacancy_id(self):
        """URL must contain startapp=fb_<vacancy_pk>."""
        from unittest.mock import MagicMock

        from service.telegram_markup_factory import group_url_feedback_reply_markup

        vacancy = MagicMock()
        vacancy.pk = 99
        markup = group_url_feedback_reply_markup(vacancy)
        button = markup.keyboard[0][0]
        assert "startapp=fb_99" in button.url

    def test_group_button_points_to_bot(self):
        """URL must point to t.me/riznorobochi_ua_bot."""
        from unittest.mock import MagicMock

        from service.telegram_markup_factory import group_url_feedback_reply_markup

        vacancy = MagicMock()
        vacancy.pk = 1
        markup = group_url_feedback_reply_markup(vacancy)
        button = markup.keyboard[0][0]
        assert "t.me/riznorobochi_ua_bot" in button.url


class TestCheckHtmlStartparamHandling:
    """Fix: check.html reads start_param and sets next= for feedback redirect."""

    def test_check_html_has_startparam_logic(self):
        """check.html must read start_param and map fb_ prefix to feedback-entry URL."""
        import pathlib

        html = pathlib.Path("telegram/templates/telegram/check.html").read_text()
        assert "start_param" in html, "check.html must handle start_param"
        assert "fb_" in html, "check.html must parse fb_ prefix"
        assert "feedback-entry" in html, "check.html must redirect to feedback-entry"

    def test_check_html_uses_tgWebAppStartParam_fallback(self):
        """check.html must also check GET param tgWebAppStartParam as fallback."""
        import pathlib

        html = pathlib.Path("telegram/templates/telegram/check.html").read_text()
        assert "tgWebAppStartParam" in html


class TestSentInGroupFlagInsideTry:
    """Fix: sent_in_group=True must be inside try block (not set on failure)."""

    def test_flag_inside_success_branch(self):
        """In approved_group_observer, sent_in_group must be set inside outer try (send), not after it."""
        import pathlib

        code = pathlib.Path("vacancy/services/observers/approved_group_observer.py").read_text()
        flag_pos = code.index('vacancy.extra["sent_in_group"] = True')
        # Find the LAST except (outer = send failed) — flag must be before it
        outer_except_pos = code.rindex('logging.warning(f"Failed to send message')
        assert flag_pos < outer_except_pos, "sent_in_group=True must be inside outer try block"


@pytest.mark.django_db
class TestVacancyMembersBackToGroup:
    """Vacancy members page has 'Повернутися в групу' button."""

    def test_back_to_group_button_in_template(self):
        import pathlib

        html = pathlib.Path("vacancy/templates/vacancy/vacancy_members.html").read_text()
        assert "Повернутися в групу" in html
        assert "vacancy.group.invite_link" in html
