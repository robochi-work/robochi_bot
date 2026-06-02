"""Tests for vacancy_continue_search: time should only shift after work start."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone


@pytest.mark.django_db
class TestContinueSearchTimeShift:
    def test_time_not_shifted_before_work_start(self, client, employer_factory, vacancy_factory):
        """Before work start time: original start_time stays unchanged."""
        owner = employer_factory()
        # Work starts in 3 hours from now (future)
        future = timezone.localtime(timezone.now()) + timedelta(hours=3)
        original_start = future.time().replace(second=0, microsecond=0)
        vacancy = vacancy_factory(
            owner=owner,
            status="stopped",
            date=future.date(),
            start_time=original_start,
            end_time=(future + timedelta(hours=4)).time().replace(second=0, microsecond=0),
            first_rollcall_passed=False,
            search_active=False,
        )
        client.force_login(owner)
        client.get(reverse("vacancy:continue_search", kwargs={"pk": vacancy.pk}))
        vacancy.refresh_from_db()
        # Start time should NOT change (work hasn't started)
        assert vacancy.start_time == original_start

    def test_time_shifted_after_work_start(self, client, employer_factory, vacancy_factory):
        """After work start time passed: start_time shifts to now + 1h."""
        owner = employer_factory()
        # Work start was 1 hour ago (past)
        past = timezone.localtime(timezone.now()) - timedelta(hours=1)
        original_start = past.time().replace(second=0, microsecond=0)
        vacancy = vacancy_factory(
            owner=owner,
            status="stopped",
            date=past.date(),
            start_time=original_start,
            end_time=(past + timedelta(hours=4)).time().replace(second=0, microsecond=0),
            first_rollcall_passed=False,
            search_active=False,
        )
        client.force_login(owner)
        client.get(reverse("vacancy:continue_search", kwargs={"pk": vacancy.pk}))
        vacancy.refresh_from_db()
        # Start time SHOULD change (work time passed)
        assert vacancy.start_time != original_start
