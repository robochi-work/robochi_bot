from unittest.mock import patch

from django.test import TestCase

from telegram.choices import STATUS_AVAILABLE, STATUS_PROCESS
from telegram.models import Channel, Group
from tests.factories import EmployerFactory
from vacancy.choices import STATUS_APPROVED, STATUS_PENDING
from vacancy.services.auto_approve import try_auto_approve


class TestAutoApprove(TestCase):
    def setUp(self):
        self.employer = EmployerFactory()
        self.city = self.employer.work_profile.city
        self.channel = Channel.objects.create(
            id=-1001, title="Test Channel", city=self.city, invite_link="https://t.me/test"
        )
        self.group = Group.objects.create(
            id=-1002, title="Test Group", status=STATUS_AVAILABLE, is_active=True, invite_link="https://t.me/grp"
        )

    def _make_vacancy(self, **kwargs):
        from tests.factories import VacancyFactory

        defaults = dict(owner=self.employer, status=STATUS_PENDING, channel=self.channel)
        defaults.update(kwargs)
        return VacancyFactory(**defaults)

    @patch("vacancy.services.auto_approve._notify_admins_auto_approved")
    def test_auto_approve_enabled(self, mock_notify):
        """Vacancy auto-approved when employer has auto_approve_vacancy=True."""
        profile = self.employer.work_profile
        profile.auto_approve_vacancy = True
        profile.save(update_fields=["auto_approve_vacancy"])

        vacancy = self._make_vacancy()
        result = try_auto_approve(vacancy)

        self.assertTrue(result)
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.status, STATUS_APPROVED)
        self.assertTrue(vacancy.search_active)
        self.assertTrue(vacancy.extra.get("auto_approved"))
        self.assertEqual(vacancy.group_id, self.group.id)
        # Group status changed to PROCESS
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, STATUS_PROCESS)
        mock_notify.assert_called_once()

    def test_auto_approve_disabled(self):
        """Vacancy NOT auto-approved when flag is False."""
        vacancy = self._make_vacancy()
        result = try_auto_approve(vacancy)

        self.assertFalse(result)
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.status, STATUS_PENDING)

    @patch("vacancy.services.auto_approve._notify_admins_auto_approved")
    def test_auto_approve_no_group_available(self, mock_notify):
        """Vacancy stays pending when no groups available."""
        profile = self.employer.work_profile
        profile.auto_approve_vacancy = True
        profile.save(update_fields=["auto_approve_vacancy"])

        # Make group unavailable
        self.group.status = STATUS_PROCESS
        self.group.save(update_fields=["status"])

        vacancy = self._make_vacancy()
        result = try_auto_approve(vacancy)

        self.assertFalse(result)
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.status, STATUS_PENDING)
        mock_notify.assert_not_called()

    @patch("vacancy.services.auto_approve._notify_admins_auto_approved")
    def test_auto_approve_no_channel(self, mock_notify):
        """Vacancy auto-approved assigns channel from work_profile city."""
        profile = self.employer.work_profile
        profile.auto_approve_vacancy = True
        profile.save(update_fields=["auto_approve_vacancy"])

        vacancy = self._make_vacancy()
        vacancy.channel = None
        vacancy.save(update_fields=["channel"])

        result = try_auto_approve(vacancy)

        self.assertTrue(result)
        vacancy.refresh_from_db()
        self.assertEqual(vacancy.channel_id, self.channel.id)
