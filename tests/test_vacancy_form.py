"""
Regression tests for vacancy creation form:
- Time constraints (start >= now+1h for today, duration 3-12h)
- Phone validation
- Date choice defaults
- Delete vacancy from moderation
"""

import datetime as d
from unittest.mock import patch

import pytest
from django.test import Client

from vacancy.forms import VacancyForm


@pytest.mark.django_db
class TestVacancyFormTimeValidation:
    """Test backend time validation in VacancyForm.clean()"""

    def _make_form_data(self, date_choice="now", start_h=10, start_m=0, end_h=13, end_m=0):
        return {
            "date_choice": date_choice,
            "gender": "A",
            "people_count": 2,
            "has_passport": False,
            "address": "Test address 123",
            "start_time_0": str(start_h).zfill(2),
            "start_time_1": str(start_m).zfill(2),
            "end_time_0": str(end_h).zfill(2),
            "end_time_1": str(end_m).zfill(2),
            "payment_amount": "300",
            "payment_unit": "shift",
            "payment_method": "cash",
            "skills": "Test skills",
        }

    def test_valid_duration_3h(self):
        data = self._make_form_data(date_choice="tomorrow", start_h=9, end_h=12)
        form = VacancyForm(data=data)
        form.full_clean()
        assert "start_time" not in form.errors
        assert "end_time" not in form.errors
        # Check no duration error in non_field_errors
        nfe = [str(e) for e in form.non_field_errors()]
        assert not any("3" in e and "hour" in e.lower() for e in nfe)

    def test_invalid_duration_less_than_3h(self):
        data = self._make_form_data(date_choice="tomorrow", start_h=9, end_h=11)
        form = VacancyForm(data=data)
        assert not form.is_valid()

    def test_invalid_duration_more_than_12h(self):
        data = self._make_form_data(date_choice="tomorrow", start_h=6, end_h=19)
        form = VacancyForm(data=data)
        assert not form.is_valid()

    def test_valid_duration_12h(self):
        data = self._make_form_data(date_choice="tomorrow", start_h=6, end_h=18)
        form = VacancyForm(data=data)
        form.full_clean()
        nfe = [str(e) for e in form.non_field_errors()]
        assert not any("12" in e and "hour" in e.lower() for e in nfe)

    @patch("django.utils.timezone.now")
    def test_today_start_time_too_early(self, mock_now):
        mock_now.return_value = d.datetime(2026, 4, 7, 14, 0, tzinfo=d.UTC)
        data = self._make_form_data(date_choice="now", start_h=14, start_m=30, end_h=18)
        form = VacancyForm(data=data)
        assert not form.is_valid()

    @patch("django.utils.timezone.now")
    def test_today_start_time_valid(self, mock_now):
        # UTC 06:00 → Kyiv local (EEST = UTC+3) 09:00 → min_start 10:00
        # start_h=12 is well above min_start regardless of ±1h timezone variance
        mock_now.return_value = d.datetime(2026, 4, 7, 6, 0, tzinfo=d.UTC)
        data = self._make_form_data(date_choice="now", start_h=12, end_h=15)
        form = VacancyForm(data=data)
        form.full_clean()
        nfe = [str(e) for e in form.non_field_errors()]
        assert not any("hour" in e.lower() for e in nfe)


@pytest.mark.django_db
class TestVacancyFormPhoneValidation:
    """Test phone validation in VacancyForm.clean_contact_phone()"""

    def _make_form_data(self, phone=""):
        return {
            "date_choice": "tomorrow",
            "gender": "A",
            "people_count": 2,
            "has_passport": False,
            "address": "Test address 123",
            "start_time_0": "09",
            "start_time_1": "00",
            "end_time_0": "12",
            "end_time_1": "00",
            "payment_amount": "300",
            "payment_unit": "shift",
            "payment_method": "cash",
            "skills": "Test skills",
            "contact_phone": phone,
        }

    def test_valid_phone_plus380(self):
        form = VacancyForm(data=self._make_form_data("+380501234567"))
        form.full_clean()
        assert "contact_phone" not in form.errors

    def test_valid_phone_0xx(self):
        form = VacancyForm(data=self._make_form_data("0501234567"))
        form.full_clean()
        assert "contact_phone" not in form.errors

    def test_valid_phone_380(self):
        form = VacancyForm(data=self._make_form_data("380501234567"))
        form.full_clean()
        assert "contact_phone" not in form.errors

    def test_invalid_phone_short(self):
        form = VacancyForm(data=self._make_form_data("050123"))
        assert not form.is_valid()
        assert "contact_phone" in form.errors

    def test_invalid_phone_letters(self):
        form = VacancyForm(data=self._make_form_data("phone123"))
        assert not form.is_valid()
        assert "contact_phone" in form.errors

    def test_empty_phone_ok(self):
        form = VacancyForm(data=self._make_form_data(""))
        form.full_clean()
        assert "contact_phone" not in form.errors

    def test_phone_with_spaces_valid(self):
        form = VacancyForm(data=self._make_form_data("+380 50 123 45 67"))
        form.full_clean()
        assert "contact_phone" not in form.errors


@pytest.mark.django_db
class TestVacancyCreateView:
    """Test vacancy create view — date defaults and time auto-adjustment"""

    def test_default_date_is_today(self, employer_factory):
        user = employer_factory()
        c = Client(SERVER_NAME="robochi.pp.ua")
        c.force_login(user)
        resp = c.get("/vacancy/create/", SERVER_NAME="robochi.pp.ua")
        assert resp.status_code == 200
        content = resp.content.decode()
        # Check that "now" radio is checked
        assert 'value="now"' in content

    def test_tomorrow_param(self, employer_factory):
        user = employer_factory()
        c = Client(SERVER_NAME="robochi.pp.ua")
        c.force_login(user)
        resp = c.get("/vacancy/create/?date=tomorrow", SERVER_NAME="robochi.pp.ua")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert 'value="tomorrow"' in content

    def test_modals_present(self, employer_factory):
        user = employer_factory()
        c = Client(SERVER_NAME="robochi.pp.ua")
        c.force_login(user)
        resp = c.get("/vacancy/create/", SERVER_NAME="robochi.pp.ua")
        content = resp.content.decode()
        assert "time-modal" in content
        assert "time-min-modal" in content
        assert "time-max-modal" in content
        assert "phone-modal" in content


@pytest.mark.django_db
class TestAdminDeleteVacancy:
    """Test admin delete vacancy view"""

    def test_delete_vacancy(self, employer_factory, vacancy_factory):
        from vacancy.models import Vacancy

        admin = employer_factory(is_staff=True)
        vacancy = vacancy_factory(owner=admin)
        vacancy_id = vacancy.pk
        c = Client(SERVER_NAME="robochi.pp.ua")
        c.force_login(admin)
        resp = c.post(f"/work/admin-panel/vacancy/{vacancy_id}/delete/", SERVER_NAME="robochi.pp.ua")
        assert resp.status_code == 302
        assert not Vacancy.objects.filter(pk=vacancy_id).exists()
