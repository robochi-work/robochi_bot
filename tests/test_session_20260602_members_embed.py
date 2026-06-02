"""Regression tests for session 02.06.2026.

Covers:
1. Members section embedded in vacancy_detail (separate members page removed).
2. vacancy_members URL redirects to detail.
3. MEMBER status only set on real group entry (not on bot confirm).
4. continue_search shifts time only after work start.
5. before_start detects recent joiners via VacancyUser.updated_at.
"""

from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from telegram.choices import CallStatus, CallType, Status
from vacancy.choices import STATUS_APPROVED
from vacancy.models import VacancyUser, VacancyUserCall


@pytest.mark.django_db
class TestMembersEmbedded:
    def test_detail_shows_members_section(self, client, employer_factory, vacancy_factory):
        """Vacancy detail page renders the embedded members section, not a separate button."""
        owner = employer_factory()
        vacancy = vacancy_factory(owner=owner, status="approved")
        client.force_login(owner)
        response = client.get(reverse("vacancy:detail", kwargs={"pk": vacancy.pk}))
        content = response.content.decode()
        assert response.status_code == 200
        # Old separate-page button must be gone
        assert "Додавання/Видалення працівників" not in content
        # New section title present
        assert "Робітники" in content

    def test_members_url_redirects_to_detail(self, client, employer_factory, vacancy_factory):
        """Legacy /members/ URL redirects to /detail/ for backward compatibility."""
        owner = employer_factory()
        vacancy = vacancy_factory(owner=owner, status="approved")
        client.force_login(owner)
        response = client.get(reverse("vacancy:members", kwargs={"pk": vacancy.pk}))
        assert response.status_code == 302
        assert f"/vacancy/{vacancy.pk}/detail/" in response.url


@pytest.mark.django_db
class TestMemberStatusOnGroupEntry:
    def test_confirm_keeps_pending_until_group_entry(self, worker_factory, vacancy_factory):
        """Bot confirm keeps PENDING_CONFIRM; MEMBER set only on real group entry."""
        from unittest.mock import patch

        from telegram.handlers.callback.call import confirm_before_start_call
        from telegram.handlers.common import CallbackStorage as Storage

        worker = worker_factory()
        vacancy = vacancy_factory(owner=worker_factory(), status="approved")
        vu = VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.PENDING_CONFIRM.value)
        VacancyUserCall.objects.create(
            vacancy_user=vu,
            call_type=CallType.WORKER_JOIN_CONFIRM.value,
            status=CallStatus.SENT.value,
        )
        cb_data = Storage.call_handler.new(
            call_type=CallType.WORKER_JOIN_CONFIRM.value,
            status=CallStatus.CONFIRM.value,
            vacancy_id=str(vacancy.id),
        )
        from unittest.mock import MagicMock

        callback = MagicMock()
        callback.data = cb_data
        callback.from_user.id = worker.id
        callback.message.chat.id = worker.id
        callback.message.message_id = 1
        with patch("telegram.handlers.callback.call.bot"):
            confirm_before_start_call(callback, user=worker)
        vu.refresh_from_db()
        # Still PENDING_CONFIRM — MEMBER is set by group.py on actual entry
        assert vu.status == Status.PENDING_CONFIRM.value


@pytest.mark.django_db
class TestContinueSearchTime:
    def test_no_shift_before_work_start(self, client, employer_factory, vacancy_factory):
        owner = employer_factory()
        future = timezone.localtime(timezone.now()) + timedelta(hours=3)
        original = future.time().replace(second=0, microsecond=0)
        v = vacancy_factory(
            owner=owner,
            status="stopped",
            date=future.date(),
            start_time=original,
            end_time=(future + timedelta(hours=4)).time().replace(second=0, microsecond=0),
            first_rollcall_passed=False,
            search_active=False,
        )
        client.force_login(owner)
        client.get(reverse("vacancy:continue_search", kwargs={"pk": v.pk}))
        v.refresh_from_db()
        assert v.start_time == original

    def test_shift_after_work_start(self, client, employer_factory, vacancy_factory):
        owner = employer_factory()
        past = timezone.localtime(timezone.now()) - timedelta(hours=1)
        original = past.time().replace(second=0, microsecond=0)
        v = vacancy_factory(
            owner=owner,
            status="stopped",
            date=past.date(),
            start_time=original,
            end_time=(past + timedelta(hours=4)).time().replace(second=0, microsecond=0),
            first_rollcall_passed=False,
            search_active=False,
        )
        client.force_login(owner)
        client.get(reverse("vacancy:continue_search", kwargs={"pk": v.pk}))
        v.refresh_from_db()
        assert v.start_time != original


@pytest.mark.django_db
class TestBeforeStartRecentJoiner:
    def test_recent_joiner_skipped(self, worker_factory, vacancy_factory, group_factory):
        """Worker whose updated_at is after the 2h-before mark is skipped."""
        from unittest.mock import MagicMock

        from vacancy.services.observers.call_observer import VacancyBeforeCallObserver

        worker = worker_factory()
        group = group_factory()
        now = timezone.now()
        start_local = (now + timedelta(hours=1)).astimezone(timezone.get_current_timezone()).time()
        v = vacancy_factory(
            owner=worker_factory(), status=STATUS_APPROVED, group=group, date=date.today(), start_time=start_local
        )
        vu = VacancyUser.objects.create(user=worker, vacancy=v, status=Status.MEMBER)
        # updated_at is now (just joined) → after 2h-before mark → must be skipped
        VacancyBeforeCallObserver(MagicMock()).check_before_start(v)
        assert not VacancyUserCall.objects.filter(vacancy_user=vu, call_type=CallType.BEFORE_START.value).exists()

    def test_early_joiner_gets_call(self, worker_factory, vacancy_factory, group_factory):
        """Worker who joined long ago (updated_at before 2h mark) still gets before_start."""
        from unittest.mock import MagicMock

        from vacancy.services.observers.call_observer import VacancyBeforeCallObserver

        worker = worker_factory()
        group = group_factory()
        now = timezone.now()
        start_local = (now + timedelta(hours=1)).astimezone(timezone.get_current_timezone()).time()
        v = vacancy_factory(
            owner=worker_factory(), status=STATUS_APPROVED, group=group, date=date.today(), start_time=start_local
        )
        vu = VacancyUser.objects.create(user=worker, vacancy=v, status=Status.MEMBER)
        VacancyUser.objects.filter(pk=vu.pk).update(updated_at=now - timedelta(hours=3))
        VacancyBeforeCallObserver(MagicMock()).check_before_start(v)
        assert VacancyUserCall.objects.filter(vacancy_user=vu, call_type=CallType.BEFORE_START.value).exists()
