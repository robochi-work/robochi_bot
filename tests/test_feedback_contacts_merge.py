"""
Regression tests for the «Відгуки/Контакти merge» (18.05.2026).

Covers:
1.  vacancy_feedback_redirect — role-based routing (worker / employer / admin / anon / 404)
2.  vacancy_members — owner card excluded for non-staff; visible to admin
3.  vacancy_members — contact_phone sourced from VacancyContactPhone, not user.phone_number
4.  group_url_feedback_reply_markup — WebApp button text, style, and URL
5.  vacancy_reinvite_worker — URL and import are gone (dead code removed)
6.  process_start_payload — type=feedback falls through to False (handler removed)
"""

import base64
import json
from unittest.mock import MagicMock, patch

import pytest
from django.urls import NoReverseMatch, reverse

from tests.factories import EmployerFactory, UserFactory, VacancyFactory, WorkerFactory

# ===========================================================================
# 1. TestVacancyFeedbackRedirect
# ===========================================================================


@pytest.mark.django_db
class TestVacancyFeedbackRedirect:
    """vacancy_feedback_redirect routes to the correct destination by role."""

    def test_worker_redirects_to_my_work(self, client):
        """A worker hitting /vacancy/<pk>/feedback-entry/ is sent to their work page."""
        employer = EmployerFactory()
        worker = WorkerFactory()
        vacancy = VacancyFactory(owner=employer, status="approved")

        client.force_login(worker)
        url = reverse("vacancy:feedback_entry", kwargs={"pk": vacancy.pk})
        response = client.get(url)

        assert response.status_code == 302
        assert response["Location"] == reverse("work:worker_my_work")

    def test_employer_redirects_to_members(self, client):
        """The vacancy owner is sent to the members management page."""
        employer = EmployerFactory()
        vacancy = VacancyFactory(owner=employer, status="approved")

        client.force_login(employer)
        url = reverse("vacancy:feedback_entry", kwargs={"pk": vacancy.pk})
        response = client.get(url)

        assert response.status_code == 302
        assert response["Location"] == reverse("vacancy:members", kwargs={"pk": vacancy.pk})

    def test_admin_redirects_to_members(self, client):
        """A staff user is sent to the members page regardless of ownership."""
        employer = EmployerFactory()
        admin = UserFactory(is_staff=True)
        vacancy = VacancyFactory(owner=employer, status="approved")

        client.force_login(admin)
        url = reverse("vacancy:feedback_entry", kwargs={"pk": vacancy.pk})
        response = client.get(url)

        assert response.status_code == 302
        assert response["Location"] == reverse("vacancy:members", kwargs={"pk": vacancy.pk})

    def test_anonymous_redirects_to_login(self, client):
        """Unauthenticated request is rejected by @login_required."""
        employer = EmployerFactory()
        vacancy = VacancyFactory(owner=employer, status="approved")

        url = reverse("vacancy:feedback_entry", kwargs={"pk": vacancy.pk})
        response = client.get(url)

        assert response.status_code == 302
        assert "check-web-app" in response["Location"] or "/login" in response["Location"]

    def test_nonexistent_vacancy_returns_404(self, client):
        """A vacancy pk that doesn't exist should yield 404, not 500."""
        worker = WorkerFactory()
        client.force_login(worker)

        url = reverse("vacancy:feedback_entry", kwargs={"pk": 999999})
        response = client.get(url)

        assert response.status_code == 404


# ===========================================================================
# 2. TestVacancyMembersOwnerExclusion
# ===========================================================================


@pytest.mark.django_db
class TestVacancyMembersOwnerExclusion:
    """vacancy_members hides the owner card for non-staff requests."""

    def test_employer_does_not_see_own_card(self, client):
        """Vacancy owner must NOT appear in members_list when they open the page themselves."""
        from vacancy.models import VacancyUser

        employer = EmployerFactory()
        vacancy = VacancyFactory(owner=employer, status="approved")
        # Add the owner to VacancyUser so there is something to exclude
        VacancyUser.objects.create(user=employer, vacancy=vacancy)

        client.force_login(employer)
        url = reverse("vacancy:members", kwargs={"pk": vacancy.pk})
        response = client.get(url)

        assert response.status_code == 200
        members_list = response.context["members_list"]
        owner_entries = [m for m in members_list if m["user"] == employer]
        assert owner_entries == [], "Owner must not appear in their own members_list"

    def test_admin_sees_owner_card(self, client):
        """Staff admin sees the owner card when they open the members page."""
        from vacancy.models import VacancyUser

        employer = EmployerFactory()
        admin = UserFactory(is_staff=True)
        vacancy = VacancyFactory(owner=employer, status="approved")
        VacancyUser.objects.create(user=employer, vacancy=vacancy)

        client.force_login(admin)
        url = reverse("vacancy:members", kwargs={"pk": vacancy.pk})
        response = client.get(url)

        assert response.status_code == 200
        members_list = response.context["members_list"]
        owner_entries = [m for m in members_list if m["user"] == employer]
        assert len(owner_entries) == 1, "Admin must see the owner card in members_list"

    def test_workers_visible_to_employer(self, client):
        """Workers who joined the vacancy ARE included in members_list for the employer."""
        from vacancy.models import VacancyUser

        employer = EmployerFactory()
        worker = WorkerFactory()
        vacancy = VacancyFactory(owner=employer, status="approved")
        VacancyUser.objects.create(user=worker, vacancy=vacancy)

        client.force_login(employer)
        url = reverse("vacancy:members", kwargs={"pk": vacancy.pk})
        response = client.get(url)

        assert response.status_code == 200
        members_list = response.context["members_list"]
        worker_entries = [m for m in members_list if m["user"] == worker]
        assert len(worker_entries) == 1, "Worker must appear in employer's members_list"


# ===========================================================================
# 3. TestVacancyMembersContactPhone
# ===========================================================================


@pytest.mark.django_db
class TestVacancyMembersContactPhone:
    """contact_phone in members_list comes from VacancyContactPhone, not user.phone_number."""

    def test_contact_phone_from_vacancy_contact_phone(self, client):
        """When a VacancyContactPhone record exists, its phone is shown — not user.phone_number."""
        from vacancy.models import VacancyContactPhone, VacancyUser

        employer = EmployerFactory()
        worker = WorkerFactory()
        # Give the worker a different phone on the user object to confirm we read from the snapshot
        worker.phone_number = "+380999999999"
        worker.save(update_fields=["phone_number"])

        vacancy = VacancyFactory(owner=employer, status="approved")
        VacancyUser.objects.create(user=worker, vacancy=vacancy)
        VacancyContactPhone.objects.create(vacancy=vacancy, user=worker, phone="+380501234567")

        client.force_login(employer)
        url = reverse("vacancy:members", kwargs={"pk": vacancy.pk})
        response = client.get(url)

        assert response.status_code == 200
        members_list = response.context["members_list"]
        worker_entry = next(m for m in members_list if m["user"] == worker)
        assert worker_entry["contact_phone"] == "+380501234567", (
            "contact_phone must come from VacancyContactPhone, not user.phone_number"
        )

    def test_empty_contact_phone_when_no_record(self, client):
        """When no VacancyContactPhone exists for the user, contact_phone is an empty string."""
        from vacancy.models import VacancyUser

        employer = EmployerFactory()
        worker = WorkerFactory()
        vacancy = VacancyFactory(owner=employer, status="approved")
        VacancyUser.objects.create(user=worker, vacancy=vacancy)
        # Deliberately no VacancyContactPhone created

        client.force_login(employer)
        url = reverse("vacancy:members", kwargs={"pk": vacancy.pk})
        response = client.get(url)

        assert response.status_code == 200
        members_list = response.context["members_list"]
        worker_entry = next(m for m in members_list if m["user"] == worker)
        assert worker_entry["contact_phone"] == "", (
            "contact_phone must be '' when no VacancyContactPhone exists for this user"
        )


# ===========================================================================
# 4. TestGroupFeedbackButton
# ===========================================================================


class TestGroupFeedbackButton:
    """group_url_feedback_reply_markup returns a primary-style WebApp button."""

    def _make_markup(self):
        """Build the markup with settings patched so reverse() works."""

        vacancy = MagicMock()
        vacancy.pk = 42

        with (
            patch("service.telegram_markup_factory.settings") as mock_settings,
            patch(
                "service.telegram_markup_factory.reverse",
                return_value="/vacancy/42/feedback-entry/",
            ),
        ):
            mock_settings.BASE_URL = "https://example.com"
            from service.telegram_markup_factory import group_url_feedback_reply_markup

            markup = group_url_feedback_reply_markup(vacancy)

        return markup

    def test_button_text_is_feedback_kontakty(self):
        """Button text must be «Відгуки/Контакти»."""
        markup = self._make_markup()
        button = markup.keyboard[0][0]
        assert button.text == "Відгуки/Контакти"

    def test_button_is_webapp_not_url(self):
        """Button must carry a web_app attribute (WebAppInfo), not a plain url string."""
        from telebot.types import WebAppInfo

        markup = self._make_markup()
        button = markup.keyboard[0][0]
        assert isinstance(button.web_app, WebAppInfo), "Button must be a WebApp button, not a URL/callback button"

    def test_webapp_url_points_to_feedback_entry(self):
        """The web_app.url must contain '/feedback-entry/' and the vacancy pk."""
        markup = self._make_markup()
        button = markup.keyboard[0][0]
        assert "/feedback-entry/" in button.web_app.url
        assert "42" in button.web_app.url

    def test_button_style_is_primary(self):
        """Button style must be 'primary' for the group pinned message."""
        markup = self._make_markup()
        button = markup.keyboard[0][0]
        assert button.style == "primary"


# ===========================================================================
# 5. TestDeprecatedReinviteRemoved
# ===========================================================================


class TestDeprecatedReinviteRemoved:
    """Sanity checks that vacancy_reinvite_worker dead code is completely gone."""

    def test_reinvite_url_does_not_exist(self):
        """reverse('vacancy:reinvite_worker', ...) must raise NoReverseMatch."""
        with pytest.raises(NoReverseMatch):
            reverse("vacancy:reinvite_worker", kwargs={"pk": 1, "user_id": 1})

    def test_reinvite_view_not_importable(self):
        """vacancy_reinvite_worker must not be importable from vacancy.views."""
        with pytest.raises(ImportError):
            from vacancy.views import vacancy_reinvite_worker  # noqa: F401


# ===========================================================================
# 6. TestFeedbackDeepLinkRemoved
# ===========================================================================


class TestFeedbackDeepLinkRemoved:
    """The type=feedback deep-link handler was removed from process_start_payload."""

    def _encode(self, data: dict) -> str:
        """Replicate encode_start_param logic from commands.py."""
        json_str = json.dumps(data, separators=(",", ":"))
        return base64.urlsafe_b64encode(json_str.encode()).decode().rstrip("=")

    def test_process_start_payload_returns_false_for_feedback_type(self):
        """process_start_payload must return False for type=feedback (handler removed)."""
        from telegram.handlers.messages.commands import process_start_payload

        payload = self._encode({"type": "feedback", "vacancy_id": 1})
        message = MagicMock()

        result = process_start_payload(payload, message)

        assert result is False, "type=feedback must not be handled — the deep-link handler was removed on 18.05.2026"
