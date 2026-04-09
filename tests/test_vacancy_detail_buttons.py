from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

User = get_user_model()


class VacancyDetailButtonVisibilityTest(TestCase):
    """Regression tests: vacancy detail hides action buttons for pending and closed statuses."""

    def setUp(self):
        from city.models import City

        self.city = City.objects.create(id=999, name="TestCity")

        self.user = User.objects.create(id=999999902, full_name="Test Employer2", phone_number="+380000000002")

        from work.models import UserWorkProfile

        UserWorkProfile.objects.create(
            user=self.user,
            role="employer",
            city=self.city,
            is_completed=True,
            agreement_accepted=True,
        )

        from telegram.models import Channel, Group

        self.channel = Channel.objects.create(
            id=-100999998,
            city=self.city,
            title="Test Channel 2",
            is_active=True,
            has_bot_administrator=True,
            invite_link="https://t.me/+test456",
        )
        self.group = Group.objects.filter(status="available").first()
        if not self.group:
            self.group = Group.objects.create(
                id=-100999997,
                title="Test Group",
                status="available",
                is_active=True,
                invite_link="https://t.me/+testgrp",
            )

    def _create_vacancy(self, status="pending"):
        from vacancy.models import Vacancy

        return Vacancy.objects.create(
            owner=self.user,
            status=status,
            date=timezone.now().date(),
            start_time=timezone.now().time(),
            end_time=timezone.now().time(),
            people_count=2,
            payment_amount=100,
            address="Test Address",
            has_passport=False,
            skills="",
            channel=self.channel,
            group=self.group,
        )

    def _get_detail(self, vacancy):
        self.client.force_login(self.user)
        return self.client.get(f"/vacancy/{vacancy.pk}/detail/")

    def test_pending_vacancy_hides_close_button(self):
        """Pending vacancy should not show Закрити вакансію button."""
        v = self._create_vacancy(status="pending")
        response = self._get_detail(v)
        self.assertNotContains(response, "Закрити вакансію")

    def test_pending_vacancy_hides_members_button(self):
        """Pending vacancy should not show Група з працівниками button."""
        v = self._create_vacancy(status="pending")
        response = self._get_detail(v)
        self.assertNotContains(response, "Група з працівниками")

    def test_pending_vacancy_hides_channel_link(self):
        """Pending vacancy should not show Загальна стрічка вакансій button."""
        v = self._create_vacancy(status="pending")
        response = self._get_detail(v)
        self.assertNotContains(response, "Загальна стрічка вакансій")

    def test_closed_vacancy_hides_members_button(self):
        """Closed vacancy should not show Група з працівниками button."""
        v = self._create_vacancy(status="closed")
        response = self._get_detail(v)
        self.assertNotContains(response, "Група з працівниками")

    def test_closed_vacancy_hides_channel_link(self):
        """Closed vacancy should not show Загальна стрічка вакансій button."""
        v = self._create_vacancy(status="closed")
        response = self._get_detail(v)
        self.assertNotContains(response, "Загальна стрічка вакансій")

    def test_approved_vacancy_shows_all_buttons(self):
        """Approved vacancy should show action buttons."""
        v = self._create_vacancy(status="approved")
        response = self._get_detail(v)
        self.assertContains(response, "Закрити вакансію")
        self.assertContains(response, "Група з працівниками")


class AdminModerationMessageDeletionTest(TestCase):
    """Test that admin_moderation_messages are stored and cleaned up."""

    def test_admin_messages_stored_in_extra(self):
        """Verify vacancy.extra can store admin_moderation_messages dict."""
        from city.models import City
        from vacancy.models import Vacancy

        city = City.objects.create(id=998, name="TestCity2")
        user = User.objects.create(id=999999903, full_name="Test Emp3", phone_number="+380000000003")

        from work.models import UserWorkProfile

        UserWorkProfile.objects.create(
            user=user,
            role="employer",
            city=city,
            is_completed=True,
            agreement_accepted=True,
        )

        v = Vacancy.objects.create(
            owner=user,
            status="pending",
            date=timezone.now().date(),
            start_time=timezone.now().time(),
            end_time=timezone.now().time(),
            people_count=1,
            payment_amount=50,
            address="Test",
            has_passport=False,
            skills="",
            extra={"admin_moderation_messages": {"123456": 789}},
        )
        v.refresh_from_db()
        self.assertEqual(v.extra["admin_moderation_messages"], {"123456": 789})

    def test_admin_messages_cleanup(self):
        """Verify admin_moderation_messages can be removed from extra."""
        from city.models import City
        from vacancy.models import Vacancy

        city = City.objects.create(id=997, name="TestCity3")
        user = User.objects.create(id=999999904, full_name="Test Emp4", phone_number="+380000000004")

        from work.models import UserWorkProfile

        UserWorkProfile.objects.create(
            user=user,
            role="employer",
            city=city,
            is_completed=True,
            agreement_accepted=True,
        )

        v = Vacancy.objects.create(
            owner=user,
            status="pending",
            date=timezone.now().date(),
            start_time=timezone.now().time(),
            end_time=timezone.now().time(),
            people_count=1,
            payment_amount=50,
            address="Test",
            has_passport=False,
            skills="",
            extra={"admin_moderation_messages": {"123": 456}, "other_key": True},
        )
        v.extra.pop("admin_moderation_messages", None)
        v.save(update_fields=["extra"])
        v.refresh_from_db()
        self.assertNotIn("admin_moderation_messages", v.extra)
        self.assertTrue(v.extra["other_key"])
