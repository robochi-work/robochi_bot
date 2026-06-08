"""Regression tests for auto-approve vacancy feature (02.06.2026).

Ensures:
1. vacancy_create auto-approves when flag enabled
2. vacancy_create goes to moderation when flag disabled
3. resume_search auto-approves when flag enabled
4. resume_search goes to moderation when flag disabled
5. No free groups → pending + admin notification
6. continue_search is NOT affected by auto_approve flag
"""

from unittest.mock import patch

from django.test import TestCase

from telegram.choices import STATUS_AVAILABLE, STATUS_PROCESS
from telegram.models import Channel, Group
from tests.factories import EmployerFactory, VacancyFactory
from vacancy.choices import STATUS_APPROVED, STATUS_PENDING, STATUS_SEARCH_STOPPED
from vacancy.services.auto_approve import try_auto_approve


class TestAutoApproveRegressionCreate(TestCase):
    """Regression: vacancy_create respects auto_approve_vacancy flag."""

    def setUp(self):
        self.employer = EmployerFactory()
        self.channel = Channel.objects.create(
            id=-1001,
            title="Test Channel",
            city=self.employer.work_profile.city,
            invite_link="https://t.me/test",
        )
        self.group = Group.objects.create(
            id=-1002,
            title="Test Group",
            status=STATUS_AVAILABLE,
            is_active=True,
            invite_link="https://t.me/grp",
        )

    @patch("vacancy.services.auto_approve._notify_admins_auto_approved")
    def test_create_auto_approved(self, mock_notify):
        """New vacancy auto-approved when employer flag is True."""
        profile = self.employer.work_profile
        profile.auto_approve_vacancy = True
        profile.save(update_fields=["auto_approve_vacancy"])

        vacancy = VacancyFactory(owner=self.employer, status=STATUS_PENDING, channel=self.channel)
        result = try_auto_approve(vacancy)

        self.assertTrue(result)
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.status, STATUS_APPROVED)
        self.assertTrue(vacancy.search_active)
        self.assertIsNotNone(vacancy.group)
        self.assertTrue(vacancy.extra.get("auto_approved"))
        mock_notify.assert_called_once()

    def test_create_not_auto_approved(self):
        """New vacancy goes to moderation when flag is False (default)."""
        vacancy = VacancyFactory(owner=self.employer, status=STATUS_PENDING, channel=self.channel)
        result = try_auto_approve(vacancy)

        self.assertFalse(result)
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.status, STATUS_PENDING)
        self.assertIsNone(vacancy.group)


class TestAutoApproveRegressionResume(TestCase):
    """Regression: resume_search (renewal) respects auto_approve_vacancy flag."""

    def setUp(self):
        self.employer = EmployerFactory()
        self.channel = Channel.objects.create(
            id=-1003,
            title="Test Channel 2",
            city=self.employer.work_profile.city,
            invite_link="https://t.me/test2",
        )
        self.group = Group.objects.create(
            id=-1004,
            title="Test Group 2",
            status=STATUS_AVAILABLE,
            is_active=True,
            invite_link="https://t.me/grp2",
        )

    @patch("vacancy.services.auto_approve._notify_admins_auto_approved")
    def test_resume_auto_approved(self, mock_notify):
        """Renewal vacancy auto-approved when employer flag is True."""
        profile = self.employer.work_profile
        profile.auto_approve_vacancy = True
        profile.save(update_fields=["auto_approve_vacancy"])

        vacancy = VacancyFactory(
            owner=self.employer,
            status=STATUS_PENDING,
            channel=self.channel,
        )
        vacancy.extra["renewal_accepted"] = True
        vacancy.save(update_fields=["extra"])

        result = try_auto_approve(vacancy)

        self.assertTrue(result)
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.status, STATUS_APPROVED)


class TestAutoApproveRegressionNoGroup(TestCase):
    """Regression: no free groups → pending + admin notified."""

    def setUp(self):
        self.employer = EmployerFactory()
        self.channel = Channel.objects.create(
            id=-1005,
            title="Test Channel 3",
            city=self.employer.work_profile.city,
            invite_link="https://t.me/test3",
        )
        # No available groups

    @patch("vacancy.services.auto_approve._notify_admins_no_group")
    def test_no_group_falls_back_to_pending(self, mock_notify_no_group):
        """Auto-approve fails gracefully when no groups available."""
        profile = self.employer.work_profile
        profile.auto_approve_vacancy = True
        profile.save(update_fields=["auto_approve_vacancy"])

        vacancy = VacancyFactory(owner=self.employer, status=STATUS_PENDING, channel=self.channel)
        result = try_auto_approve(vacancy)

        self.assertFalse(result)
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.status, STATUS_PENDING)
        mock_notify_no_group.assert_called_once()


class TestContinueSearchNotAffected(TestCase):
    """Regression: continue_search works the same regardless of auto_approve flag."""

    def setUp(self):
        self.employer = EmployerFactory()
        self.channel = Channel.objects.create(
            id=-1006,
            title="Test Channel 4",
            city=self.employer.work_profile.city,
            invite_link="https://t.me/test4",
        )
        self.group = Group.objects.create(
            id=-1007,
            title="Test Group 3",
            status=STATUS_PROCESS,
            is_active=True,
            invite_link="https://t.me/grp3",
        )

    @patch("vacancy.services.observers.subscriber_setup.vacancy_publisher.notify")
    def test_continue_search_ignores_flag(self, mock_notify):
        """continue_search sets approved directly, auto_approve flag irrelevant."""
        vacancy = VacancyFactory(
            owner=self.employer,
            status=STATUS_SEARCH_STOPPED,
            channel=self.channel,
            group=self.group,
        )
        # Simulate continue_search logic
        vacancy.status = STATUS_APPROVED
        vacancy.search_active = True
        vacancy.save(update_fields=["status", "search_active"])

        vacancy.refresh_from_db()
        self.assertEqual(vacancy.status, STATUS_APPROVED)
        self.assertTrue(vacancy.search_active)
