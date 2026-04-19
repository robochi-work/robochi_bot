from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

User = get_user_model()


class EmployerCitiesViewTest(TestCase):
    """Regression tests for employer cities page and channel link button."""

    def setUp(self):
        from city.models import City
        from telegram.models import Channel

        self.factory = RequestFactory()
        self.user = User.objects.create(
            id=999999901,
            full_name="Test Employer",
            phone_number="+380991234567",
        )

        # City must exist before UserWorkProfile (FK constraint)
        self.city = City.objects.create(id=901)

        # Channel for that city — needed for employer_cities and employer_dashboard to show the link
        self.channel = Channel.objects.create(
            id=-100999999901,
            city=self.city,
            title="Test Channel",
            is_active=True,
            has_bot_administrator=True,
            invite_link="https://t.me/+test123abc",
        )

    def _create_profile(self, multi_city=False):
        from work.models import UserWorkProfile

        profile, _ = UserWorkProfile.objects.get_or_create(
            user=self.user,
            defaults={
                "role": "employer",
                "city": self.city,
                "is_completed": True,
                "agreement_accepted": True,
            },
        )
        profile.multi_city_enabled = multi_city
        profile.save()
        return profile

    def _create_vacancy(self):
        """Create a minimal vacancy so the dashboard doesn't redirect to vacancy:create."""
        from django.utils import timezone

        from telegram.models import Group
        from vacancy.models import Vacancy

        group = Group.objects.filter(status="available").first()
        return Vacancy.objects.create(
            owner=self.user,
            status="approved",
            date=timezone.now().date(),
            start_time=timezone.now().time(),
            end_time=timezone.now().time(),
            people_count=2,
            payment_amount=100,
            address="Test Address",
            has_passport=False,
            skills="Test skills",
            channel=self.channel,
            group=group,
        )

    def _login_and_get(self, url):
        self.client.force_login(self.user)
        return self.client.get(url)

    def test_employer_cities_page_renders_for_single_city(self):
        """Single-city employer should see employer_cities page with correct heading."""
        self._create_profile(multi_city=False)
        response = self._login_and_get("/work/employer/cities/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Загальна стрічка вакансій")

    def test_employer_dashboard_has_channel_link_to_cities_page(self):
        """Dashboard button should always link to employer_cities page URL."""
        self._create_profile(multi_city=False)
        self._create_vacancy()
        response = self._login_and_get("/")
        self.assertEqual(response.status_code, 200)
        # The channel button should point to the cities page
        self.assertContains(response, "/work/employer/cities/")
        # The channel button href should NOT be a direct t.me link
        content = response.content.decode()
        # employer_cities URL should be present as a button href
        self.assertIn('href="/work/employer/cities/"', content)

    def test_employer_cities_uses_open_telegram_link(self):
        """Channel links should use openTelegramLink JS, not target=_blank."""
        self._create_profile(multi_city=False)
        response = self._login_and_get("/work/employer/cities/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Should NOT have target=_blank for channel links
        self.assertNotIn('target="_blank"', content)
        # Should use Telegram WebApp API
        self.assertIn("openTelegramLink", content)

    def test_vacancy_detail_has_channel_link(self):
        """Vacancy detail page should contain channel link button."""
        self._create_profile(multi_city=False)
        vacancy = self._create_vacancy()
        if vacancy:
            response = self._login_and_get(f"/vacancy/{vacancy.pk}/detail/")
            self.assertContains(response, "Загальна стрічка вакансій")
