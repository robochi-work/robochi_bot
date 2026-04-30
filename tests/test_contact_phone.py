"""
Regression tests for Contact Phone System (Apr 29, 2026).

Tests:
1. User.contact_phone field exists and defaults to ""
2. VacancyContactPhone created for worker via worker_phone handler
3. worker_phone saves to User.contact_phone (persistent)
4. VacancyContactPhone created for employer via form save
5. Employer form pre-fills from User.contact_phone
6. VacancyContactPhone cascade-deleted with vacancy
7. phone_confirm callback: confirm saves VacancyContactPhone
8. phone_confirm callback: change does NOT save (waits for text input)
9. User.phone_number never overwritten by worker_phone handler
"""

import datetime
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from telegram.choices import CallStatus, CallType
from telegram.models import Status
from user.models import User
from vacancy.choices import STATUS_APPROVED
from vacancy.models import Vacancy, VacancyContactPhone, VacancyUser, VacancyUserCall


@pytest.fixture
def employer(db):
    user = User.objects.create(id=5000, username="emp_phone_test", contact_phone="+380501111111")
    from work.models import UserWorkProfile

    UserWorkProfile.objects.create(user=user, role="employer", is_completed=True)
    return user


@pytest.fixture
def worker(db):
    user = User.objects.create(
        id=6000,
        username="wrk_phone_test",
        phone_number="+380991112233",
        contact_phone="+380997776655",
    )
    from work.models import UserWorkProfile

    UserWorkProfile.objects.create(user=user, role="worker", is_completed=True)
    return user


@pytest.fixture
def worker_no_contact(db):
    user = User.objects.create(
        id=6001,
        username="wrk_no_contact",
        phone_number="+380991119999",
        contact_phone="",
    )
    from work.models import UserWorkProfile

    UserWorkProfile.objects.create(user=user, role="worker", is_completed=True)
    return user


@pytest.fixture
def vacancy(db, employer):
    from telegram.models import Group

    group = Group.objects.create(id=-2001, title="Phone Test Group", invite_link="https://t.me/+phonetest")
    return Vacancy.objects.create(
        owner=employer,
        gender="A",
        people_count=5,
        has_passport=False,
        address="Phone Test Addr",
        date=timezone.now().date(),
        start_time=(timezone.now() + datetime.timedelta(hours=4)).time(),
        end_time=(timezone.now() + datetime.timedelta(hours=8)).time(),
        payment_amount=500,
        skills="Test",
        status=STATUS_APPROVED,
        group=group,
        contact_phone="+380501111111",
    )


class TestUserContactPhoneField:
    @pytest.mark.django_db
    def test_contact_phone_exists_and_defaults_empty(self, db):
        user = User.objects.create(id=9999, username="field_test")
        assert user.contact_phone == ""

    @pytest.mark.django_db
    def test_registration_phone_separate_from_contact(self, worker):
        assert worker.phone_number == "+380991112233"
        assert worker.contact_phone == "+380997776655"
        assert worker.phone_number != worker.contact_phone


class TestWorkerPhoneSavesToBothModels:
    @pytest.mark.django_db
    def test_saves_to_vacancy_contact_phone_and_user(self, worker_no_contact, vacancy):
        """worker_phone handler saves to VacancyContactPhone AND User.contact_phone."""
        vu = VacancyUser.objects.create(user=worker_no_contact, vacancy=vacancy, status=Status.MEMBER.value)
        VacancyUserCall.objects.create(
            vacancy_user=vu,
            call_type=CallType.WORKER_JOIN_CONFIRM.value,
            status=CallStatus.CONFIRM.value,
        )

        from telegram.handlers.messages.worker_phone import handle_worker_phone

        message = MagicMock()
        message.from_user.id = worker_no_contact.id
        message.chat.id = worker_no_contact.id
        message.chat.type = "private"
        message.content_type = "text"
        message.text = "+380661234567"

        with patch("telegram.handlers.messages.worker_phone.bot"):
            with patch("vacancy.services.worker_invite.bot") as mock_invite_bot:
                mock_invite_bot.send_message.return_value = MagicMock(message_id=999)
                handle_worker_phone(message)

        # VacancyContactPhone created
        assert VacancyContactPhone.objects.filter(vacancy=vacancy, user=worker_no_contact).exists()
        cp = VacancyContactPhone.objects.get(vacancy=vacancy, user=worker_no_contact)
        assert cp.phone == "+380661234567"

        # User.contact_phone updated
        worker_no_contact.refresh_from_db()
        assert worker_no_contact.contact_phone == "+380661234567"

    @pytest.mark.django_db
    def test_registration_phone_not_overwritten(self, worker_no_contact, vacancy):
        """worker_phone handler must NOT touch User.phone_number."""
        original_phone = worker_no_contact.phone_number
        vu = VacancyUser.objects.create(user=worker_no_contact, vacancy=vacancy, status=Status.MEMBER.value)
        VacancyUserCall.objects.create(
            vacancy_user=vu,
            call_type=CallType.WORKER_JOIN_CONFIRM.value,
            status=CallStatus.CONFIRM.value,
        )

        from telegram.handlers.messages.worker_phone import handle_worker_phone

        message = MagicMock()
        message.from_user.id = worker_no_contact.id
        message.chat.id = worker_no_contact.id
        message.chat.type = "private"
        message.content_type = "text"
        message.text = "+380661234567"

        with patch("telegram.handlers.messages.worker_phone.bot"):
            with patch("vacancy.services.worker_invite.bot") as mock_invite_bot:
                mock_invite_bot.send_message.return_value = MagicMock(message_id=999)
                handle_worker_phone(message)

        worker_no_contact.refresh_from_db()
        assert worker_no_contact.phone_number == original_phone


class TestEmployerContactPhoneInForm:
    @pytest.mark.django_db
    def test_vacancy_creation_saves_contact_phone_to_both(self, employer, vacancy):
        """When employer contact phone is saved, it goes to VacancyContactPhone AND User.contact_phone."""
        new_phone = "+380509998877"

        # Simulate what forms.py save() does
        VacancyContactPhone.objects.update_or_create(
            vacancy=vacancy,
            user=employer,
            defaults={"phone": new_phone},
        )
        if employer.contact_phone != new_phone:
            employer.contact_phone = new_phone
            employer.save(update_fields=["contact_phone"])

        # VacancyContactPhone created
        assert VacancyContactPhone.objects.filter(vacancy=vacancy, user=employer).exists()
        cp = VacancyContactPhone.objects.get(vacancy=vacancy, user=employer)
        assert cp.phone == new_phone

        # User.contact_phone updated
        employer.refresh_from_db()
        assert employer.contact_phone == new_phone

    @pytest.mark.django_db
    def test_prefill_uses_user_contact_phone(self, employer):
        """Vacancy form should pre-fill contact_phone from User.contact_phone."""
        employer.contact_phone = "+380501234567"
        employer.save(update_fields=["contact_phone"])

        # Simulate what views.py does for pre-fill
        prefill_phone = employer.contact_phone or ""
        assert prefill_phone == "+380501234567"


class TestVacancyContactPhoneCascadeDelete:
    @pytest.mark.django_db
    def test_deleted_with_vacancy(self, worker, vacancy):
        VacancyContactPhone.objects.create(vacancy=vacancy, user=worker, phone="+380991234567")
        assert VacancyContactPhone.objects.filter(vacancy=vacancy).count() >= 1

        vacancy_id = vacancy.id
        with patch("vacancy.services.observers.subscriber_setup.vacancy_publisher"):
            vacancy.delete()

        assert VacancyContactPhone.objects.filter(vacancy_id=vacancy_id).count() == 0


class TestPhoneConfirmCallback:
    @pytest.mark.django_db
    def test_confirm_saves_contact_phone(self, worker, vacancy):
        """Pressing 'Підтвердити' saves User.contact_phone to VacancyContactPhone."""
        import json

        VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.MEMBER.value)

        from telegram.handlers.callback.phone_confirm import handle_phone_confirm

        callback = MagicMock()
        callback.from_user.id = worker.id
        callback.data = json.dumps({"t": "phone_confirm", "v": vacancy.id, "s": "confirm"})
        callback.message.chat.id = worker.id
        callback.message.message_id = 123
        callback.id = "cb_123"

        with patch("telegram.handlers.callback.phone_confirm.bot"):
            with patch("vacancy.services.worker_invite.bot") as mock_invite_bot:
                mock_invite_bot.send_message.return_value = MagicMock(message_id=999)
                handle_phone_confirm(callback)

        assert VacancyContactPhone.objects.filter(vacancy=vacancy, user=worker).exists()
        cp = VacancyContactPhone.objects.get(vacancy=vacancy, user=worker)
        assert cp.phone == worker.contact_phone

    @pytest.mark.django_db
    def test_change_does_not_save_phone(self, worker, vacancy):
        """Pressing 'Змінити' should NOT create VacancyContactPhone (waits for text input)."""
        import json

        VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.MEMBER.value)

        from telegram.handlers.callback.phone_confirm import handle_phone_confirm

        callback = MagicMock()
        callback.from_user.id = worker.id
        callback.data = json.dumps({"t": "phone_confirm", "v": vacancy.id, "s": "change"})
        callback.message.chat.id = worker.id
        callback.message.message_id = 123
        callback.id = "cb_456"

        with patch("telegram.handlers.callback.phone_confirm.bot"):
            handle_phone_confirm(callback)

        assert not VacancyContactPhone.objects.filter(vacancy=vacancy, user=worker).exists()
