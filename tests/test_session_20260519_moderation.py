import pytest
from django.urls import reverse

from tests.factories import ChannelFactory, EmployerFactory, GroupFactory, UserFactory, VacancyFactory


@pytest.mark.django_db
class TestAdminModerationFromVacancyList:
    """Regression: pending vacancy cards in admin view link to moderation form, not detail page."""

    def _setup(self):
        from city.models import City

        admin = UserFactory(is_staff=True)
        employer = EmployerFactory()
        city = City.objects.create(id=99, name="TestModCity")
        channel = ChannelFactory(city=city)
        group = GroupFactory(status="available")
        return admin, employer, city, channel, group

    def test_pending_vacancy_card_links_to_moderation(self, client):
        """Admin viewing employer's vacancy list: pending vacancy card href = moderation URL."""
        admin, employer, city, channel, group = self._setup()
        vacancy = VacancyFactory(owner=employer, channel=channel, group=group, status="pending")

        client.force_login(admin)
        url = reverse("vacancy:my_list") + f"?for_user={employer.pk}"
        response = client.get(url)
        content = response.content.decode()

        moderate_url = reverse("work:admin_moderate_vacancy", kwargs={"vacancy_id": vacancy.pk})
        detail_url = reverse("vacancy:detail", kwargs={"pk": vacancy.pk})

        assert response.status_code == 200
        assert moderate_url in content, "Pending vacancy card must link to moderation form"
        assert f'href="{detail_url}"' not in content, "Pending vacancy card must NOT link to detail page"

    def test_approved_vacancy_card_links_to_detail(self, client):
        """Admin viewing employer's vacancy list: non-pending vacancy card href = detail URL."""
        admin, employer, city, channel, group = self._setup()
        vacancy = VacancyFactory(owner=employer, channel=channel, group=group, status="approved")

        client.force_login(admin)
        url = reverse("vacancy:my_list") + f"?for_user={employer.pk}"
        response = client.get(url)
        content = response.content.decode()

        detail_url = reverse("vacancy:detail", kwargs={"pk": vacancy.pk})
        assert response.status_code == 200
        assert detail_url in content, "Approved vacancy card must link to detail page"

    def test_employer_sees_detail_link_for_pending(self, client):
        """Employer (non-admin) always sees detail link, even for pending vacancy."""
        from city.models import City

        employer = EmployerFactory()
        city = City.objects.create(id=99, name="TestModCity")
        channel = ChannelFactory(city=city)
        group = GroupFactory(status="available")
        vacancy = VacancyFactory(owner=employer, channel=channel, group=group, status="pending")

        client.force_login(employer)
        url = reverse("vacancy:my_list")
        response = client.get(url)
        content = response.content.decode()

        detail_url = reverse("vacancy:detail", kwargs={"pk": vacancy.pk})
        assert response.status_code == 200
        assert detail_url in content, "Employer must see detail link, not moderation link"
