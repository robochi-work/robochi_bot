"""Regression: 'Через 2 години' must NOT be re-sent after continue_search.

Bug: continue_search shifted start_time and deleted all VacancyUserCall
records. Next Celery tick re-found the vacancy inside the new 2h window,
found no BEFORE_START record, and re-sent the message.

Fix: two defense layers (extra["pre_call_done"] flag and
extra["original_start_datetime"] anchor). Both set at vacancy creation
and on cycle restart (resume_search / renewal / admin moderation).
continue_search does NOT touch either — same cycle.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone


@pytest.mark.django_db
class TestBeforeStartNoRepeatAfterContinueSearch:
    def test_filter_skips_when_pre_call_done(self, employer_factory, vacancy_factory):
        """Layer 1: filter must skip vacancies with extra['pre_call_done']."""
        from vacancy.tasks.call import get_before_start_vacancies

        owner = employer_factory()
        now = timezone.localtime(timezone.now())
        future_start = now + timedelta(minutes=90)
        v = vacancy_factory(
            owner=owner,
            status="approved",
            date=future_start.date(),
            start_time=future_start.time().replace(second=0, microsecond=0),
            end_time=(future_start + timedelta(hours=4)).time().replace(second=0, microsecond=0),
        )
        orig_aware = timezone.make_aware(datetime.combine(v.date, v.start_time), timezone.get_current_timezone())
        v.extra = {"original_start_datetime": orig_aware.isoformat(), "pre_call_done": True}
        v.save(update_fields=["extra"])

        result = list(get_before_start_vacancies())
        assert v not in result

    def test_filter_uses_original_datetime_anchor(self, employer_factory, vacancy_factory):
        """Layer 2: filter must compare against original_start_datetime, not live start_time."""
        from vacancy.tasks.call import get_before_start_vacancies

        owner = employer_factory()
        now = timezone.localtime(timezone.now())
        # Original cycle start: 3h in the past — outside the 2h window.
        original = now - timedelta(hours=3)
        # Live start_time: 90 min in the future — would match without anchor.
        future = now + timedelta(minutes=90)
        v = vacancy_factory(
            owner=owner,
            status="approved",
            date=future.date(),
            start_time=future.time().replace(second=0, microsecond=0),
            end_time=(future + timedelta(hours=4)).time().replace(second=0, microsecond=0),
        )
        v.extra = {"original_start_datetime": original.isoformat()}
        v.save(update_fields=["extra"])

        result = list(get_before_start_vacancies())
        assert v not in result

    def test_continue_search_preserves_pre_call_flags(self, client, employer_factory, vacancy_factory):
        """continue_search must NOT pop original_start_datetime nor pre_call_done."""
        owner = employer_factory()
        now = timezone.localtime(timezone.now())
        past_start = now - timedelta(minutes=30)  # work_time_passed → continue_search shifts time
        v = vacancy_factory(
            owner=owner,
            status="approved",
            date=past_start.date(),
            start_time=past_start.time().replace(second=0, microsecond=0),
            end_time=(past_start + timedelta(hours=5)).time().replace(second=0, microsecond=0),
            search_active=True,
        )
        orig_iso = timezone.make_aware(
            datetime.combine(v.date, v.start_time), timezone.get_current_timezone()
        ).isoformat()
        v.extra = {"original_start_datetime": orig_iso, "pre_call_done": True}
        v.save(update_fields=["extra"])

        client.force_login(owner)
        with patch("vacancy.services.observers.subscriber_setup.vacancy_publisher.notify"):
            client.get(reverse("vacancy:continue_search", kwargs={"pk": v.pk}))

        v.refresh_from_db()
        assert v.extra.get("pre_call_done") is True
        assert v.extra.get("original_start_datetime") == orig_iso

    def test_no_repeat_send_after_continue_search_full_flow(self, client, employer_factory, vacancy_factory):
        """End-to-end: 2h notice was sent, continue_search ran, filter still excludes vacancy."""
        from vacancy.tasks.call import get_before_start_vacancies

        owner = employer_factory()
        now = timezone.localtime(timezone.now())
        past_start = now - timedelta(minutes=30)
        v = vacancy_factory(
            owner=owner,
            status="approved",
            date=past_start.date(),
            start_time=past_start.time().replace(second=0, microsecond=0),
            end_time=(past_start + timedelta(hours=5)).time().replace(second=0, microsecond=0),
            search_active=True,
        )
        orig_iso = timezone.make_aware(
            datetime.combine(v.date, v.start_time), timezone.get_current_timezone()
        ).isoformat()
        v.extra = {"original_start_datetime": orig_iso, "pre_call_done": True}
        v.save(update_fields=["extra"])

        client.force_login(owner)
        with patch("vacancy.services.observers.subscriber_setup.vacancy_publisher.notify"):
            client.get(reverse("vacancy:continue_search", kwargs={"pk": v.pk}))

        v.refresh_from_db()
        result = list(get_before_start_vacancies())
        assert v not in result

    def test_check_before_start_sets_pre_call_done(self, employer_factory, vacancy_factory, worker_factory):
        """check_before_start must set pre_call_done after a successful dispatch."""
        from telegram.choices import Status
        from vacancy.models import VacancyUser
        from vacancy.services.observers.call_observer import VacancyBeforeCallObserver

        owner = employer_factory()
        now = timezone.localtime(timezone.now())
        future = now + timedelta(minutes=90)
        v = vacancy_factory(
            owner=owner,
            status="approved",
            date=future.date(),
            start_time=future.time().replace(second=0, microsecond=0),
            end_time=(future + timedelta(hours=4)).time().replace(second=0, microsecond=0),
        )
        v.extra = {
            "original_start_datetime": timezone.make_aware(
                datetime.combine(v.date, v.start_time), timezone.get_current_timezone()
            ).isoformat()
        }
        v.save(update_fields=["extra"])

        worker = worker_factory()
        vu = VacancyUser.objects.create(vacancy=v, user=worker, status=Status.MEMBER.value)
        # check_before_start skips workers whose updated_at is after the
        # 2h-before mark (they joined too late to need the notice). Force the
        # member to look "already there" before the 2h window opened.
        VacancyUser.objects.filter(pk=vu.pk).update(updated_at=timezone.now() - timedelta(hours=3))

        observer = VacancyBeforeCallObserver()
        with patch("vacancy.services.observers.call_observer.send_and_track", return_value=12345):
            observer.check_before_start(v)

        v.refresh_from_db()
        assert v.extra.get("pre_call_done") is True

    def test_check_before_start_skips_when_pre_call_done(self, employer_factory, vacancy_factory, worker_factory):
        """check_before_start must early-return when pre_call_done is True."""
        from telegram.choices import Status
        from vacancy.models import VacancyUser, VacancyUserCall
        from vacancy.services.observers.call_observer import VacancyBeforeCallObserver

        owner = employer_factory()
        now = timezone.localtime(timezone.now())
        future = now + timedelta(minutes=90)
        v = vacancy_factory(
            owner=owner,
            status="approved",
            date=future.date(),
            start_time=future.time().replace(second=0, microsecond=0),
            end_time=(future + timedelta(hours=4)).time().replace(second=0, microsecond=0),
        )
        v.extra = {"pre_call_done": True}
        v.save(update_fields=["extra"])

        worker = worker_factory()
        VacancyUser.objects.create(vacancy=v, user=worker, status=Status.MEMBER.value)

        observer = VacancyBeforeCallObserver()
        with patch("vacancy.services.observers.call_observer.send_and_track", return_value=12345) as mock_send:
            observer.check_before_start(v)

        mock_send.assert_not_called()
        assert not VacancyUserCall.objects.filter(vacancy_user__vacancy=v).exists()

    def test_resume_search_resets_cycle(self, client, employer_factory, vacancy_factory):
        """resume_search must clear pre_call_done and re-anchor original_start_datetime to the new time."""
        from vacancy.services.call import reset_before_start_cycle

        owner = employer_factory()
        now = timezone.localtime(timezone.now())
        v = vacancy_factory(
            owner=owner,
            status="stopped",
            date=now.date(),
            start_time=(now + timedelta(hours=3)).time().replace(second=0, microsecond=0),
            end_time=(now + timedelta(hours=7)).time().replace(second=0, microsecond=0),
        )
        old_iso = timezone.make_aware(
            datetime.combine(v.date, v.start_time), timezone.get_current_timezone()
        ).isoformat()
        v.extra = {"original_start_datetime": old_iso, "pre_call_done": True}
        v.save(update_fields=["extra"])

        # Simulate that resume_search changed start_time to a new value
        new_start = (now + timedelta(hours=5)).time().replace(second=0, microsecond=0)
        v.start_time = new_start
        v.save(update_fields=["start_time"])

        reset_before_start_cycle(v)
        v.refresh_from_db()

        assert "pre_call_done" not in v.extra
        new_iso = timezone.make_aware(
            datetime.combine(v.date, v.start_time), timezone.get_current_timezone()
        ).isoformat()
        assert v.extra["original_start_datetime"] == new_iso
        assert v.extra["original_start_datetime"] != old_iso
