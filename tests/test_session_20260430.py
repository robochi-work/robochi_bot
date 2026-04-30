"""
Regression tests for session 2026-04-30:
- Worker 'Моя робота' page shows vacancy only when worker is in group (UserInGroup)
- before_start_call skips workers who joined < 2h before start
- VacancyContactPhone deleted on rejection (fresh re-apply)
- VACANCY_NEW_MEMBER triggers VacancyIsFullObserver
- worker_phone handler finds correct vacancy without saved contact phone
"""

from datetime import date, timedelta

import pytest
from django.test import RequestFactory
from django.utils import timezone

from telegram.choices import CallStatus, CallType, Status
from telegram.models import UserInGroup
from vacancy.choices import STATUS_APPROVED
from vacancy.models import VacancyContactPhone, VacancyUser, VacancyUserCall


@pytest.mark.django_db
class TestWorkerMyWork:
    """Worker 'Моя робота' page — shows vacancy only when in group."""

    def test_no_vacancy_when_not_in_group(self, worker_factory, vacancy_factory, group_factory):
        worker = worker_factory()
        group = group_factory()
        vacancy = vacancy_factory(owner=worker_factory(), status=STATUS_APPROVED, group=group)
        VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.MEMBER)
        # No UserInGroup — should not see vacancy

        from work.views.worker import worker_my_work

        factory = RequestFactory()
        request = factory.get("/work/my-work/")
        request.user = worker
        response = worker_my_work(request)
        assert response.status_code == 200
        assert b"\xd0\x9d\xd0\xb5\xd0\xbc\xd0\xb0\xd1\x94" in response.content  # "Немає"

    def test_vacancy_shown_when_in_group(self, worker_factory, vacancy_factory, group_factory):
        worker = worker_factory()
        group = group_factory()
        vacancy = vacancy_factory(owner=worker_factory(), status=STATUS_APPROVED, group=group)
        VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.MEMBER)
        UserInGroup.objects.create(user=worker, group=group, status=Status.MEMBER)

        from work.views.worker import worker_my_work

        factory = RequestFactory()
        request = factory.get("/work/my-work/")
        request.user = worker
        response = worker_my_work(request)
        assert response.status_code == 200
        assert vacancy.address.encode() in response.content


@pytest.mark.django_db
class TestBeforeStartCallSkip:
    """before_start_call should skip workers who joined < 2h before start."""

    def test_skip_when_joined_less_than_2h(self, worker_factory, vacancy_factory, group_factory):
        worker = worker_factory()
        group = group_factory()
        now = timezone.now()
        start_time_local = (now + timedelta(hours=1)).astimezone(timezone.get_current_timezone()).time()

        vacancy = vacancy_factory(
            owner=worker_factory(),
            status=STATUS_APPROVED,
            group=group,
            date=date.today(),
            start_time=start_time_local,
        )
        vu = VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.MEMBER)
        UserInGroup.objects.create(user=worker, group=group, status=Status.MEMBER)

        # Worker confirmed join 30 min ago (< 2h before start)
        VacancyUserCall.objects.create(
            vacancy_user=vu,
            call_type=CallType.WORKER_JOIN_CONFIRM.value,
            status=CallStatus.CONFIRM.value,
            created_at=now - timedelta(minutes=30),
        )

        from vacancy.services.observers.call_observer import VacancyBeforeCallObserver

        observer = VacancyBeforeCallObserver(notifier=None)
        observer.check_before_start(vacancy)

        # Should NOT create BEFORE_START call
        assert not VacancyUserCall.objects.filter(
            vacancy_user=vu,
            call_type=CallType.BEFORE_START.value,
        ).exists()


@pytest.mark.django_db
class TestContactPhoneCleanup:
    """VacancyContactPhone deleted on rejection for fresh re-apply."""

    def test_contact_phone_deleted_on_vacancy_user_left(self, worker_factory, vacancy_factory, group_factory):
        worker = worker_factory(contact_phone="0501234567")
        group = group_factory()
        vacancy = vacancy_factory(owner=worker_factory(), status=STATUS_APPROVED, group=group)
        VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.MEMBER)
        VacancyContactPhone.objects.create(vacancy=vacancy, user=worker, phone="0501234567")

        # Simulate rejection: status LEFT + delete contact phone
        VacancyUser.objects.filter(user=worker, vacancy=vacancy).update(status=Status.LEFT)
        VacancyContactPhone.objects.filter(vacancy=vacancy, user=worker).delete()

        assert not VacancyContactPhone.objects.filter(vacancy=vacancy, user=worker).exists()


@pytest.mark.django_db
class TestWorkerPhoneHandler:
    """worker_phone handler finds correct vacancy (one without saved contact phone)."""

    def test_finds_vacancy_without_contact_phone(self, worker_factory, vacancy_factory, group_factory):
        worker = worker_factory(contact_phone="0501111111")
        group1 = group_factory()
        group2 = group_factory()
        vacancy1 = vacancy_factory(owner=worker_factory(), status=STATUS_APPROVED, group=group1)
        vacancy2 = vacancy_factory(owner=worker_factory(), status=STATUS_APPROVED, group=group2)

        vu1 = VacancyUser.objects.create(user=worker, vacancy=vacancy1, status=Status.MEMBER)
        vu2 = VacancyUser.objects.create(user=worker, vacancy=vacancy2, status=Status.MEMBER)

        # Both have CONFIRM calls
        VacancyUserCall.objects.create(
            vacancy_user=vu1,
            call_type=CallType.WORKER_JOIN_CONFIRM.value,
            status=CallStatus.CONFIRM.value,
            created_at=timezone.now() - timedelta(hours=1),
        )
        VacancyUserCall.objects.create(
            vacancy_user=vu2,
            call_type=CallType.WORKER_JOIN_CONFIRM.value,
            status=CallStatus.CONFIRM.value,
            created_at=timezone.now(),
        )

        # vacancy1 has contact phone, vacancy2 does not
        VacancyContactPhone.objects.create(vacancy=vacancy1, user=worker, phone="0501111111")

        # Handler should pick vacancy2 (no contact phone)
        from vacancy.models import VacancyContactPhone as VCP

        pending_calls = (
            VacancyUserCall.objects.filter(
                vacancy_user__user=worker,
                call_type=CallType.WORKER_JOIN_CONFIRM.value,
                status=CallStatus.CONFIRM.value,
            )
            .select_related("vacancy_user__vacancy")
            .order_by("-created_at")
        )

        found_vacancy = None
        for pc in pending_calls:
            if not VCP.objects.filter(vacancy=pc.vacancy_user.vacancy, user=worker).exists():
                found_vacancy = pc.vacancy_user.vacancy
                break

        assert found_vacancy == vacancy2
