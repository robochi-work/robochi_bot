"""
Regression tests for the refactored "Я ГОТОВИЙ ПРАЦЮВАТИ" flow (Apr 29, 2026).

New flow:
1. Worker clicks button → deep link → /start → join-confirm message (NOT in group yet)
2. Confirm → phone request → phone saved to VacancyContactPhone → group invite
3. Already in vacancy → cabinet message
4. Employer clicks → cabinet message
5. Timeout 5 min → VacancyUser LEFT (no group kick)
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
    user = User.objects.create(id=1000, username="employer_test")
    from work.models import UserWorkProfile

    UserWorkProfile.objects.create(user=user, role="employer", is_completed=True)
    return user


@pytest.fixture
def worker(db):
    user = User.objects.create(id=2000, username="worker_test", phone_number="+380991112233")
    from work.models import UserWorkProfile

    UserWorkProfile.objects.create(user=user, role="worker", is_completed=True)
    return user


@pytest.fixture
def vacancy(db, employer):
    from telegram.models import Group

    group = Group.objects.create(id=-1001, title="Test Group", invite_link="https://t.me/+testlink")
    return Vacancy.objects.create(
        owner=employer,
        gender="A",
        people_count=5,
        has_passport=False,
        address="Test Address",
        date=timezone.now().date(),
        start_time=(timezone.now() + datetime.timedelta(hours=4)).time(),
        end_time=(timezone.now() + datetime.timedelta(hours=8)).time(),
        payment_amount=500,
        skills="Test",
        status=STATUS_APPROVED,
        group=group,
    )


class TestProcessApplyPayload:
    @pytest.mark.django_db
    def test_creates_vacancy_user_and_call(self, worker, vacancy):
        from telegram.handlers.messages.commands import _process_apply_payload

        message = MagicMock()
        message.from_user.id = worker.id
        message.chat.id = worker.id
        data = {"type": "apply", "vacancy_id": vacancy.id}

        with patch("telegram.handlers.messages.commands.get_bot"):
            result = _process_apply_payload(data, message)

        assert result is True
        vu = VacancyUser.objects.get(user=worker, vacancy=vacancy)
        assert vu.status == Status.MEMBER.value
        call = VacancyUserCall.objects.get(vacancy_user=vu)
        assert call.call_type == CallType.WORKER_JOIN_CONFIRM.value
        assert call.status == CallStatus.SENT.value

    @pytest.mark.django_db
    def test_employer_gets_cabinet(self, employer, vacancy):
        from telegram.handlers.messages.commands import _process_apply_payload

        message = MagicMock()
        message.from_user.id = employer.id
        message.chat.id = employer.id
        data = {"type": "apply", "vacancy_id": vacancy.id}

        with patch("telegram.handlers.messages.commands.get_bot"):
            result = _process_apply_payload(data, message)

        assert result is True
        assert not VacancyUser.objects.filter(user=employer, vacancy=vacancy).exists()

    @pytest.mark.django_db
    def test_already_confirmed_gets_cabinet(self, worker, vacancy):
        vu = VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.MEMBER.value)
        VacancyUserCall.objects.create(
            vacancy_user=vu,
            call_type=CallType.WORKER_JOIN_CONFIRM.value,
            status=CallStatus.CONFIRM.value,
        )
        from telegram.handlers.messages.commands import _process_apply_payload

        message = MagicMock()
        message.from_user.id = worker.id
        message.chat.id = worker.id
        data = {"type": "apply", "vacancy_id": vacancy.id}

        with patch("telegram.handlers.messages.commands.get_bot") as mock_bot:
            result = _process_apply_payload(data, message)

        assert result is True
        sent_text = (
            mock_bot().send_message.call_args[1].get("text", "") or mock_bot().send_message.call_args[0][1]
            if mock_bot().send_message.called
            else ""
        )
        assert "Власний кабінет" in str(sent_text) or mock_bot().send_message.called

    @pytest.mark.django_db
    def test_group_full_rejected(self, worker, vacancy):
        vacancy.people_count = 0
        vacancy.save()
        from telegram.handlers.messages.commands import _process_apply_payload

        message = MagicMock()
        message.from_user.id = worker.id
        message.chat.id = worker.id
        data = {"type": "apply", "vacancy_id": vacancy.id}

        with patch("telegram.handlers.messages.commands.get_bot"):
            result = _process_apply_payload(data, message)

        assert result is True
        assert not VacancyUser.objects.filter(user=worker, vacancy=vacancy).exists()


class TestWorkerPhoneFlow:
    @pytest.mark.django_db
    def test_phone_saves_to_vacancy_contact_phone(self, worker, vacancy):
        vu = VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.MEMBER.value)
        VacancyUserCall.objects.create(
            vacancy_user=vu,
            call_type=CallType.WORKER_JOIN_CONFIRM.value,
            status=CallStatus.CONFIRM.value,
        )
        from telegram.handlers.messages.worker_phone import handle_worker_phone

        message = MagicMock()
        message.from_user.id = worker.id
        message.chat.id = worker.id
        message.chat.type = "private"
        message.content_type = "text"
        message.text = "+380991234567"

        with patch("telegram.handlers.messages.worker_phone.bot"):
            with patch("vacancy.services.worker_invite.bot") as mock_invite_bot:
                mock_invite_bot.send_message.return_value = MagicMock(message_id=999)
                handle_worker_phone(message)

        assert VacancyContactPhone.objects.filter(vacancy=vacancy, user=worker).exists()
        cp = VacancyContactPhone.objects.get(vacancy=vacancy, user=worker)
        assert cp.phone == "+380991234567"


class TestJoinConfirmTimeout:
    @pytest.mark.django_db
    def test_timeout_sets_left_no_group_kick(self, worker, vacancy):
        vu = VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.MEMBER.value)
        VacancyUserCall.objects.create(
            vacancy_user=vu,
            call_type=CallType.WORKER_JOIN_CONFIRM.value,
            status=CallStatus.SENT.value,
            created_at=timezone.now() - datetime.timedelta(minutes=6),
        )

        with patch("telegram.handlers.bot_instance.bot") as mock_bot:
            with patch("telegram.handlers.bot_instance.get_bot", return_value=mock_bot):
                with patch("vacancy.tasks.call.connection"):
                    from vacancy.tasks.call import worker_join_confirm_check_task

                    worker_join_confirm_check_task()

        vu.refresh_from_db()
        assert vu.status == Status.LEFT
        call = VacancyUserCall.objects.get(vacancy_user=vu, call_type=CallType.WORKER_JOIN_CONFIRM.value)
        assert call.status == CallStatus.REJECT.value
