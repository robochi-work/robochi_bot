import pytest
from django.urls import reverse

from tests.factories import ChannelFactory, EmployerFactory, GroupFactory, UserFactory, VacancyFactory


@pytest.mark.django_db
def test_admin_vacancy_list_no_block_status(client):
    """Admin views employer's vacancy list — no block-status element rendered."""
    from city.models import City

    admin = UserFactory(is_staff=True)
    employer = EmployerFactory()
    city = City.objects.create(id=99, name="TestAdminCity")
    channel = ChannelFactory(city=city)
    group = GroupFactory(status="available")
    VacancyFactory(owner=employer, channel=channel, group=group, status="approved")

    client.force_login(admin)
    url = reverse("vacancy:my_list") + "?for_user=" + str(employer.pk)
    response = client.get(url)

    assert response.status_code == 200
    # CSS defines .block-status-card but the actual element must not be rendered
    assert 'class="block-status-card"' not in response.content.decode()


@pytest.mark.django_db
def test_admin_can_access_vacancy_detail(client):
    """Admin can open vacancy:detail for another user's vacancy."""
    from city.models import City

    admin = UserFactory(is_staff=True)
    employer = EmployerFactory()
    city = City.objects.create(id=99, name="TestAdminCity")
    channel = ChannelFactory(city=city)
    group = GroupFactory(status="available")
    vacancy = VacancyFactory(owner=employer, channel=channel, group=group, status="approved")

    client.force_login(admin)
    url = reverse("vacancy:detail", kwargs={"pk": vacancy.pk})
    response = client.get(url)

    assert response.status_code == 200


@pytest.mark.django_db
def test_vacancy_form_validation_ukrainian():
    """Vacancy form with past start_time returns Ukrainian error containing 'Час початку'."""
    from vacancy.forms import VacancyForm

    # TimeSelectField is a MultiValueField — use _0 / _1 suffixes for hour/minute
    data = {
        "date_choice": "now",
        "start_time_0": "00",
        "start_time_1": "00",
        "end_time_0": "05",
        "end_time_1": "00",
        "gender": "A",
        "people_count": "2",
        "has_passport": "",
        "address": "вул. Тестова 1, Київ",
        "payment_amount": "200",
        "payment_unit": "shift",
        "payment_method": "cash",
        "skills": "Загальні роботи",
    }
    form = VacancyForm(data, work_profile=None)
    assert not form.is_valid()
    assert "Час початку" in str(form.errors)


@pytest.mark.django_db
def test_moderate_redirects_to_my_list(client):
    """After moderation POST, redirect URL contains for_user parameter.

    Uses a non-pending vacancy to trigger the early-return redirect path in
    admin_moderate_vacancy, which always redirects to vacancy:my_list?for_user=<owner>.
    This verifies the redirect URL structure without invoking the publisher chain.
    """
    from city.models import City

    admin = UserFactory(is_staff=True)
    employer = EmployerFactory()
    city = City.objects.create(id=99, name="TestAdminCity")
    channel = ChannelFactory(city=city)
    group = GroupFactory(status="available")
    # Non-pending status → view immediately redirects with for_user (no form processing)
    vacancy = VacancyFactory(owner=employer, channel=channel, group=group, status="approved")

    client.force_login(admin)
    url = reverse("work:admin_moderate_vacancy", kwargs={"vacancy_id": vacancy.pk})
    response = client.post(url, {})

    assert response.status_code == 302
    assert "for_user" in response["Location"]
