"""Regression for combined Telegram-status check + cleanup logic (09.06.2026 v3).

check_telegram_status returns ALIVE / DELETED / BOT_BLOCKED / UNKNOWN.

cleanup_inactive_users_task behaviour:
- DELETED → delete the user (positive evidence required).
- BOT_BLOCKED → create indefinite TEMPORARY block (blocked_until=None),
  do NOT delete. Block auto-released on next ALIVE (Pass 0).
- UNKNOWN → no action (fail-open).
- ALIVE → fall through to 180-day inactivity check.

Pass 0 re-evaluates existing BOT_BLOCKED blocks:
- ALIVE   → BlockService.unblock_user(block.id) — auto-release.
- DELETED → delete user (block goes with cascade).
- BOT_BLOCKED / UNKNOWN → keep the block.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestCheckTelegramStatusViaChannel:
    @patch("user.tasks.bot")
    def test_alive_when_user_in_channel_with_name(self, mock_bot):
        from telegram.models import Channel
        from user.tasks import TG_STATUS_ALIVE, _check_via_channel

        member = MagicMock()
        member.status = "member"
        member.user.first_name = "Іван"
        mock_bot.get_chat_member.return_value = member

        with patch.object(Channel.objects, "filter") as mock_ch:
            mock_ch.return_value.first.return_value = MagicMock(id=-1001)

            fake_user = MagicMock()
            fake_user.id = 111
            fake_user.work_profile = MagicMock()
            fake_user.work_profile.city = MagicMock()

            assert _check_via_channel(fake_user) == TG_STATUS_ALIVE

    @patch("user.tasks.bot")
    def test_deleted_when_user_in_channel_empty_name(self, mock_bot):
        from telegram.models import Channel
        from user.tasks import TG_STATUS_DELETED, _check_via_channel

        member = MagicMock()
        member.status = "member"
        member.user.first_name = ""
        mock_bot.get_chat_member.return_value = member

        with patch.object(Channel.objects, "filter") as mock_ch:
            mock_ch.return_value.first.return_value = MagicMock(id=-1001)

            fake_user = MagicMock()
            fake_user.id = 222
            fake_user.work_profile = MagicMock()
            fake_user.work_profile.city = MagicMock()

            assert _check_via_channel(fake_user) == TG_STATUS_DELETED

    @patch("user.tasks.bot")
    def test_returns_none_when_user_left_channel(self, mock_bot):
        """User not in channel: cannot determine from channel alone — fallback to private chat."""
        from telegram.models import Channel
        from user.tasks import _check_via_channel

        member = MagicMock()
        member.status = "left"
        member.user.first_name = ""
        mock_bot.get_chat_member.return_value = member

        with patch.object(Channel.objects, "filter") as mock_ch:
            mock_ch.return_value.first.return_value = MagicMock(id=-1001)

            fake_user = MagicMock()
            fake_user.id = 333
            fake_user.work_profile = MagicMock()
            fake_user.work_profile.city = MagicMock()

            assert _check_via_channel(fake_user) is None

    def test_returns_none_when_no_city(self):
        from user.tasks import _check_via_channel

        fake_user = MagicMock()
        fake_user.id = 444
        fake_user.work_profile = None

        assert _check_via_channel(fake_user) is None


class TestCheckViaPrivateChat:
    @patch("user.tasks.bot")
    def test_bot_blocked_classified_correctly(self, mock_bot):
        from user.tasks import TG_STATUS_BOT_BLOCKED, _check_via_private_chat

        mock_bot.get_chat.side_effect = Exception("Forbidden: bot was blocked by the user")
        assert _check_via_private_chat(555) == TG_STATUS_BOT_BLOCKED

    @patch("user.tasks.bot")
    def test_chat_not_found_classified_as_bot_blocked(self, mock_bot):
        from user.tasks import TG_STATUS_BOT_BLOCKED, _check_via_private_chat

        mock_bot.get_chat.side_effect = Exception("Bad Request: chat not found")
        assert _check_via_private_chat(666) == TG_STATUS_BOT_BLOCKED

    @patch("user.tasks.bot")
    def test_other_errors_unknown(self, mock_bot):
        from user.tasks import TG_STATUS_UNKNOWN, _check_via_private_chat

        mock_bot.get_chat.side_effect = TimeoutError("read timeout")
        assert _check_via_private_chat(777) == TG_STATUS_UNKNOWN

    @patch("user.tasks.bot")
    def test_alive_via_private_chat(self, mock_bot):
        from user.tasks import TG_STATUS_ALIVE, _check_via_private_chat

        chat = MagicMock()
        chat.first_name = "Олена"
        mock_bot.get_chat.return_value = chat
        assert _check_via_private_chat(888) == TG_STATUS_ALIVE

    @patch("user.tasks.bot")
    def test_deleted_via_private_chat(self, mock_bot):
        from user.tasks import TG_STATUS_DELETED, _check_via_private_chat

        chat = MagicMock()
        chat.first_name = "Deleted Account"
        mock_bot.get_chat.return_value = chat
        assert _check_via_private_chat(999) == TG_STATUS_DELETED


@pytest.mark.django_db
class TestCleanupPass1:
    """Pass 1: every regular user."""

    @patch("user.tasks.check_telegram_status")
    def test_deleted_account_is_removed(self, mock_status):
        from user.models import User
        from user.tasks import TG_STATUS_DELETED, cleanup_inactive_users_task

        User.objects.create(id=100001, username="ghost")
        mock_status.return_value = TG_STATUS_DELETED

        cleanup_inactive_users_task()

        assert not User.objects.filter(id=100001).exists()

    @patch("user.tasks.check_telegram_status")
    def test_bot_blocked_creates_indefinite_temp_block(self, mock_status):
        """Bot-blocked user → indefinite TEMPORARY block (blocked_until=None)."""
        from user.choices import BlockReason, BlockType
        from user.models import User, UserBlock
        from user.tasks import TG_STATUS_BOT_BLOCKED, cleanup_inactive_users_task

        User.objects.create(id=100002, username="blocked_us")
        mock_status.return_value = TG_STATUS_BOT_BLOCKED

        cleanup_inactive_users_task()

        assert User.objects.filter(id=100002).exists()
        block = UserBlock.objects.filter(user_id=100002, is_active=True, reason=BlockReason.BOT_BLOCKED).first()
        assert block is not None
        assert block.block_type == BlockType.TEMPORARY
        assert block.blocked_until is None, "Block must be indefinite — released only on next ALIVE check"

    @patch("user.tasks.check_telegram_status")
    def test_bot_blocked_does_not_duplicate_block(self, mock_status):
        from user.choices import BlockReason, BlockType
        from user.models import User, UserBlock
        from user.tasks import TG_STATUS_BOT_BLOCKED, cleanup_inactive_users_task

        u = User.objects.create(id=100003, username="dup_block")
        UserBlock.objects.create(
            user=u,
            block_type=BlockType.TEMPORARY,
            reason=BlockReason.BOT_BLOCKED,
            blocked_until=None,
            is_active=True,
        )
        mock_status.return_value = TG_STATUS_BOT_BLOCKED

        cleanup_inactive_users_task()

        count = UserBlock.objects.filter(user_id=100003, reason=BlockReason.BOT_BLOCKED).count()
        assert count == 1

    @patch("user.tasks.check_telegram_status")
    def test_unknown_status_takes_no_action(self, mock_status):
        from user.models import User, UserBlock
        from user.tasks import TG_STATUS_UNKNOWN, cleanup_inactive_users_task

        User.objects.create(id=100004, username="transient")
        mock_status.return_value = TG_STATUS_UNKNOWN

        cleanup_inactive_users_task()

        assert User.objects.filter(id=100004).exists()
        assert not UserBlock.objects.filter(user_id=100004).exists()


@pytest.mark.django_db
class TestCleanupPass0BotBlockedRecheck:
    """Pass 0: re-evaluate existing BOT_BLOCKED blocks."""

    @patch("user.tasks.check_telegram_status")
    def test_alive_user_gets_auto_unblocked(self, mock_status):
        """User unblocked the bot → BOT_BLOCKED record auto-released."""
        from user.choices import BlockReason, BlockType
        from user.models import User, UserBlock
        from user.tasks import TG_STATUS_ALIVE, cleanup_inactive_users_task

        u = User.objects.create(id=200001, username="reborn")
        UserBlock.objects.create(
            user=u,
            block_type=BlockType.TEMPORARY,
            reason=BlockReason.BOT_BLOCKED,
            blocked_until=None,
            is_active=True,
        )
        mock_status.return_value = TG_STATUS_ALIVE

        cleanup_inactive_users_task()

        active = UserBlock.objects.filter(user_id=200001, is_active=True, reason=BlockReason.BOT_BLOCKED).exists()
        assert not active, "Block must be auto-released when user is ALIVE"
        assert User.objects.filter(id=200001).exists()

    @patch("user.tasks.check_telegram_status")
    def test_deleted_user_with_existing_bot_block_is_removed(self, mock_status):
        """Bot-blocked + later deleted Telegram account → delete user."""
        from user.choices import BlockReason, BlockType
        from user.models import User, UserBlock
        from user.tasks import TG_STATUS_DELETED, cleanup_inactive_users_task

        u = User.objects.create(id=200002, username="gone_for_good")
        UserBlock.objects.create(
            user=u,
            block_type=BlockType.TEMPORARY,
            reason=BlockReason.BOT_BLOCKED,
            blocked_until=None,
            is_active=True,
        )
        mock_status.return_value = TG_STATUS_DELETED

        cleanup_inactive_users_task()

        assert not User.objects.filter(id=200002).exists()

    @patch("user.tasks.check_telegram_status")
    def test_still_bot_blocked_keeps_existing_block(self, mock_status):
        from user.choices import BlockReason, BlockType
        from user.models import User, UserBlock
        from user.tasks import TG_STATUS_BOT_BLOCKED, cleanup_inactive_users_task

        u = User.objects.create(id=200003, username="still_blocking")
        UserBlock.objects.create(
            user=u,
            block_type=BlockType.TEMPORARY,
            reason=BlockReason.BOT_BLOCKED,
            blocked_until=None,
            is_active=True,
        )
        mock_status.return_value = TG_STATUS_BOT_BLOCKED

        cleanup_inactive_users_task()

        active = UserBlock.objects.filter(user_id=200003, is_active=True, reason=BlockReason.BOT_BLOCKED).count()
        assert active == 1
        assert User.objects.filter(id=200003).exists()

    @patch("user.tasks.check_telegram_status")
    def test_unknown_status_for_blocked_user_keeps_block(self, mock_status):
        """Transient API error must NOT release the block (fail-open also for un-blocking)."""
        from user.choices import BlockReason, BlockType
        from user.models import User, UserBlock
        from user.tasks import TG_STATUS_UNKNOWN, cleanup_inactive_users_task

        u = User.objects.create(id=200004, username="api_flaky")
        UserBlock.objects.create(
            user=u,
            block_type=BlockType.TEMPORARY,
            reason=BlockReason.BOT_BLOCKED,
            blocked_until=None,
            is_active=True,
        )
        mock_status.return_value = TG_STATUS_UNKNOWN

        cleanup_inactive_users_task()

        active = UserBlock.objects.filter(user_id=200004, is_active=True, reason=BlockReason.BOT_BLOCKED).exists()
        assert active
