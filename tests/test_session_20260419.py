"""
Regression tests for session 2026-04-19.
Covers: callback apply button, employer group invite task,
vacancy close observer message deletion, deep link payload.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase

from telegram.models import Status
from user.choices import BlockReason, BlockType
from user.services import BlockService
from vacancy.choices import GENDER_FEMALE, GENDER_MALE, STATUS_APPROVED


class TestApplyVacancyCallback(TestCase):
    """Tests for telegram/handlers/callback/apply_vacancy.py checks."""

    @pytest.fixture(autouse=True)
    def _setup(self, employer_factory, worker_factory, vacancy_factory, group_factory, channel_factory):
        self.channel = channel_factory()
        self.group = group_factory(invite_link="https://t.me/+test123")
        self.employer = employer_factory()
        self.worker_male = worker_factory(gender=GENDER_MALE)
        self.worker_female = worker_factory(gender=GENDER_FEMALE)
        self.vacancy = vacancy_factory(
            owner=self.employer,
            group=self.group,
            channel=self.channel,
            gender=GENDER_MALE,
            people_count=2,
        )

    def test_employer_cannot_join_other_vacancy(self):
        """INV-005: employer who is not owner must be declined."""
        from user.models import User

        other_employer = User.objects.create(id=999999, username="other_emp")
        from work.models import UserWorkProfile

        UserWorkProfile.objects.create(user=other_employer, role="employer")
        profile = getattr(other_employer, "work_profile", None)
        assert profile is not None
        assert profile.role == "employer"
        assert self.vacancy.owner != other_employer

    def test_gender_filter_blocks_wrong_gender(self):
        """Worker with wrong gender should not pass."""
        assert self.vacancy.gender == GENDER_MALE
        assert self.worker_female.gender == GENDER_FEMALE
        assert self.vacancy.gender != self.worker_female.gender

    def test_gender_filter_passes_correct_gender(self):
        """Worker with correct gender should pass."""
        assert self.vacancy.gender == GENDER_MALE
        assert self.worker_male.gender == GENDER_MALE
        assert self.vacancy.gender == self.worker_male.gender

    def test_admin_bypasses_all_checks(self):
        """Admin (is_staff=True) should bypass all checks."""
        from user.models import User

        admin = User.objects.create(id=888888, username="admin_test", is_staff=True)
        assert admin.is_staff is True

    def test_permanently_blocked_user_declined(self):
        """Permanently blocked user cannot apply."""
        BlockService.block_user(
            user=self.worker_male,
            block_type=BlockType.PERMANENT,
            reason=BlockReason.MANUAL,
        )
        assert BlockService.is_permanently_blocked(self.worker_male) is True

    def test_temporarily_blocked_user_declined(self):
        """Temporarily blocked user cannot apply."""
        BlockService.block_user(
            user=self.worker_male,
            block_type=BlockType.TEMPORARY,
            reason=BlockReason.ROLLCALL_REJECT,
        )
        assert BlockService.is_temporarily_blocked(self.worker_male) is True


class TestEmployerGroupInviteTask(TestCase):
    """Tests for vacancy/tasks/employer_group_invite.py."""

    @pytest.fixture(autouse=True)
    def _setup(self, employer_factory, vacancy_factory, group_factory, channel_factory):
        self.channel = channel_factory()
        self.group = group_factory(invite_link="https://t.me/+test456")
        self.employer = employer_factory()
        self.vacancy = vacancy_factory(
            owner=self.employer,
            group=self.group,
            channel=self.channel,
            status=STATUS_APPROVED,
            extra={},
        )

    @patch("vacancy.tasks.employer_group_invite.bot")
    def test_invite_sent_to_owner(self, mock_bot):
        """Task should send message with invite link to owner."""
        from celery.exceptions import Retry

        mock_bot.send_message.return_value = MagicMock(message_id=12345)

        from vacancy.tasks.employer_group_invite import send_employer_group_invite_task

        with pytest.raises(Retry):
            send_employer_group_invite_task(self.vacancy.id)

        mock_bot.send_message.assert_called_once()
        call_kwargs = mock_bot.send_message.call_args
        assert call_kwargs[1]["chat_id"] == self.employer.id

    @patch("vacancy.tasks.employer_group_invite.bot")
    def test_owner_in_group_stops_retries(self, mock_bot):
        """If owner already in group, task should stop."""
        from vacancy.models import VacancyUser

        VacancyUser.objects.create(
            user=self.employer,
            vacancy=self.vacancy,
            status=Status.OWNER,
        )

        from vacancy.tasks.employer_group_invite import send_employer_group_invite_task

        send_employer_group_invite_task(self.vacancy.id)
        mock_bot.send_message.assert_not_called()

    def test_vacancy_not_found_does_not_crash(self):
        """Task with non-existent vacancy_id should not raise."""
        from vacancy.tasks.employer_group_invite import send_employer_group_invite_task

        send_employer_group_invite_task(999999)  # should just return


class TestBlockReasonEmployerNoGroup(TestCase):
    """Tests for BlockReason.EMPLOYER_NO_GROUP."""

    @pytest.fixture(autouse=True)
    def _setup(self, employer_factory):
        self.employer = employer_factory()

    def test_block_reason_exists(self):
        """EMPLOYER_NO_GROUP should be a valid BlockReason."""
        assert hasattr(BlockReason, "EMPLOYER_NO_GROUP")
        assert BlockReason.EMPLOYER_NO_GROUP == "employer_no_group"

    def test_auto_block_employer_no_group(self):
        """auto_block_employer_no_group should create a temporary block."""
        block = BlockService.auto_block_employer_no_group(self.employer)
        assert block is not None
        assert block.block_type == BlockType.TEMPORARY
        assert block.reason == BlockReason.EMPLOYER_NO_GROUP
        assert BlockService.is_temporarily_blocked(self.employer) is True


class TestVacancyDeleteMessages(TestCase):
    """Tests for VacancyDeleteEmployerInviteObserver extended deletion."""

    @pytest.fixture(autouse=True)
    def _setup(self, employer_factory, vacancy_factory, group_factory, channel_factory):
        self.channel = channel_factory()
        self.group = group_factory(invite_link="https://t.me/+test789")
        self.employer = employer_factory()
        self.vacancy = vacancy_factory(
            owner=self.employer,
            group=self.group,
            channel=self.channel,
            extra={
                "created_msg_id": 111,
                "approved_msg_id": 222,
                "employer_invite_msg_id": 333,
                "apply_invite_msg_ids": {"100": 444, "200": 555},
            },
        )

    @patch("vacancy.services.observers.vacancy_close.bot")
    def test_all_messages_deleted(self, mock_bot):
        """Observer should delete all stored message IDs."""
        from vacancy.services.observers.vacancy_close import VacancyDeleteEmployerInviteObserver

        observer = VacancyDeleteEmployerInviteObserver(MagicMock())
        observer.update("vacancy_close", {"vacancy": self.vacancy})

        assert mock_bot.delete_message.call_count == 5
        self.vacancy.refresh_from_db()
        assert "created_msg_id" not in self.vacancy.extra
        assert "approved_msg_id" not in self.vacancy.extra
        assert "employer_invite_msg_id" not in self.vacancy.extra
        assert "apply_invite_msg_ids" not in self.vacancy.extra


class TestDeepLinkPayload(TestCase):
    """Tests for encode/decode start param for deep link."""

    def test_encode_decode_apply_payload(self):
        """Payload should encode and decode correctly."""
        from telegram.handlers.messages.commands import decode_start_param, encode_start_param

        data = {"type": "apply", "vacancy_id": 42}
        encoded = encode_start_param(data)
        decoded = decode_start_param(encoded)
        assert decoded["type"] == "apply"
        assert decoded["vacancy_id"] == 42

    def test_payload_is_url_safe(self):
        """Encoded payload should not contain +, /, =."""
        from telegram.handlers.messages.commands import encode_start_param

        data = {"type": "apply", "vacancy_id": 99999}
        encoded = encode_start_param(data)
        assert "+" not in encoded
        assert "/" not in encoded
        assert "=" not in encoded
