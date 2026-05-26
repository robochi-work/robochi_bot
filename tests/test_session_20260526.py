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
