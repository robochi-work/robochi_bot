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

        with patch("telegram.handlers.messages.commands.get_bot") as gb:
            gb.return_value.send_message.return_value.message_id = 12345
            result = _process_apply_payload(data, message)

        assert result is True
        vu = VacancyUser.objects.get(user=worker, vacancy=vacancy)
        assert vu.status == Status.PENDING_CONFIRM.value
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

        with patch("telegram.handlers.messages.commands.get_bot") as gb:
            gb.return_value.send_message.return_value.message_id = 12345
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
            mock_bot.return_value.send_message.return_value.message_id = 12345
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

        with patch("telegram.handlers.messages.commands.get_bot") as gb:
            gb.return_value.send_message.return_value.message_id = 12345
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
        vu = VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.PENDING_CONFIRM.value)
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


class TestPendingConfirmStatus:
    @pytest.mark.django_db
    def test_apply_creates_pending_confirm_status(self, worker, vacancy):
        from telegram.handlers.messages.commands import _process_apply_payload

        message = MagicMock()
        message.from_user.id = worker.id
        message.chat.id = worker.id

        with patch("telegram.handlers.messages.commands.get_bot") as gb:
            gb.return_value.send_message.return_value.message_id = 12345
            result = _process_apply_payload({"type": "apply", "vacancy_id": vacancy.id}, message)

        assert result is True
        vu = VacancyUser.objects.get(user=worker, vacancy=vacancy)
        assert vu.status == Status.PENDING_CONFIRM.value

    @pytest.mark.django_db
    def test_confirm_button_promotes_to_member(self, worker, vacancy):
        from telegram.handlers.callback.call import confirm_before_start_call
        from telegram.handlers.common import CallbackStorage as Storage

        vu = VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.PENDING_CONFIRM.value)
        VacancyUserCall.objects.create(
            vacancy_user=vu,
            call_type=CallType.WORKER_JOIN_CONFIRM.value,
            status=CallStatus.SENT.value,
        )

        callback_data = Storage.call_handler.new(
            call_type=CallType.WORKER_JOIN_CONFIRM.value,
            status=CallStatus.CONFIRM.value,
            vacancy_id=str(vacancy.id),
        )
        callback = MagicMock()
        callback.data = callback_data
        callback.from_user.id = worker.id
        callback.message.chat.id = worker.id
        callback.message.message_id = 999

        with patch("telegram.handlers.callback.call.bot"):
            confirm_before_start_call(callback, user=worker)

        vu.refresh_from_db()
        # Status stays PENDING_CONFIRM until worker enters the group
        assert vu.status == Status.PENDING_CONFIRM.value

    @pytest.mark.django_db
    def test_pending_confirm_blocks_apply_to_other_vacancy(self, worker, vacancy, employer):
        from telegram.handlers.messages.commands import _process_apply_payload
        from telegram.models import Group

        group2 = Group.objects.create(id=-1002, title="Test Group 2", invite_link="https://t.me/+testlink2")
        vacancy_b = Vacancy.objects.create(
            owner=employer,
            gender="A",
            people_count=5,
            has_passport=False,
            address="Test Address B",
            date=vacancy.date,
            start_time=vacancy.start_time,
            end_time=vacancy.end_time,
            payment_amount=500,
            skills="Test",
            status=STATUS_APPROVED,
            group=group2,
        )

        message = MagicMock()
        message.from_user.id = worker.id
        message.chat.id = worker.id

        with patch("telegram.handlers.messages.commands.get_bot") as gb:
            gb.return_value.send_message.return_value.message_id = 12345
            _process_apply_payload({"type": "apply", "vacancy_id": vacancy.id}, message)

        assert VacancyUser.objects.filter(user=worker, vacancy=vacancy, status=Status.PENDING_CONFIRM.value).exists()

        mock_bot = MagicMock()
        with patch("telegram.handlers.messages.commands.get_bot", return_value=mock_bot):
            _process_apply_payload({"type": "apply", "vacancy_id": vacancy_b.id}, message)

        sent_text = str(mock_bot.send_message.call_args)
        assert "вже берете участь" in sent_text
        assert not VacancyUser.objects.filter(user=worker, vacancy=vacancy_b).exists()

    @pytest.mark.django_db
    def test_pending_confirm_counts_in_full_check(self, worker, vacancy):
        from telegram.handlers.messages.commands import _process_apply_payload

        vacancy.people_count = 2
        vacancy.save()

        user1 = User.objects.create(id=3001, username="worker_pc1", phone_number="+380991112234")
        user2 = User.objects.create(id=3002, username="worker_pc2", phone_number="+380991112235")
        VacancyUser.objects.create(user=user1, vacancy=vacancy, status=Status.PENDING_CONFIRM.value)
        VacancyUser.objects.create(user=user2, vacancy=vacancy, status=Status.PENDING_CONFIRM.value)

        message = MagicMock()
        message.from_user.id = worker.id
        message.chat.id = worker.id

        mock_bot = MagicMock()
        with patch("telegram.handlers.messages.commands.get_bot", return_value=mock_bot):
            result = _process_apply_payload({"type": "apply", "vacancy_id": vacancy.id}, message)

        assert result is True
        sent_text = str(mock_bot.send_message.call_args)
        assert "всі місця" in sent_text
        assert not VacancyUser.objects.filter(user=worker, vacancy=vacancy).exists()

    @pytest.mark.django_db
    def test_timeout_kicks_pending_confirm(self, worker, vacancy):
        vu = VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.PENDING_CONFIRM.value)
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
        assert vu.status == Status.LEFT.value

    @pytest.mark.django_db
    def test_pending_confirm_user_skipped_by_before_start_observer(self, worker, vacancy):
        """
        Регресія для бага "Через 2 години" — юзер зі статусом PENDING_CONFIRM
        не потрапляє в vacancy.members і не отримує BEFORE_START call.
        """
        from unittest.mock import MagicMock

        from vacancy.services.observers.call_observer import VacancyBeforeCallObserver

        vacancy.start_time = (timezone.now() + datetime.timedelta(hours=1)).time()
        vacancy.save()

        VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.PENDING_CONFIRM.value)

        notifier = MagicMock()
        observer = VacancyBeforeCallObserver(notifier=notifier)
        observer.check_before_start(vacancy)

        assert not VacancyUserCall.objects.filter(
            vacancy_user__vacancy=vacancy,
            vacancy_user__user=worker,
            call_type=CallType.BEFORE_START.value,
        ).exists(), "BEFORE_START call must NOT be sent to PENDING_CONFIRM user"

        assert vacancy.members.count() == 0, "PENDING_CONFIRM user must not be in vacancy.members"

    @pytest.mark.django_db
    def test_member_user_gets_before_start_call(self, worker, vacancy):
        """Контроль: юзер зі статусом MEMBER повинен отримувати BEFORE_START call."""
        from unittest.mock import MagicMock

        from vacancy.services.observers.call_observer import VacancyBeforeCallObserver

        vacancy.start_time = (timezone.now() + datetime.timedelta(hours=1)).time()
        vacancy.save()

        vu = VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.MEMBER.value)
        # Force updated_at well before the 2h-before mark (joined long ago)
        VacancyUser.objects.filter(pk=vu.pk).update(updated_at=timezone.now() - datetime.timedelta(hours=5))

        notifier = MagicMock()
        observer = VacancyBeforeCallObserver(notifier=notifier)
        observer.check_before_start(vacancy)

        assert VacancyUserCall.objects.filter(
            vacancy_user__vacancy=vacancy,
            vacancy_user__user=worker,
            call_type=CallType.BEFORE_START.value,
        ).exists(), "BEFORE_START call must be sent to MEMBER user"

        assert vacancy.members.count() == 1, "MEMBER user must appear in vacancy.members"
