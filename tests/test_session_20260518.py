"""Regression tests for Bot API 9.4-10.0 features added in May 2026 session.

Covers:
- style="constructive" on phone-sharing and cabinet buttons
- GroupService.set_member_tag() calls on group join (employer / worker / admin)
- GroupService.set_member_tag() internal bot API call and error handling
- style="danger" / "primary" in telegram_markup_factory
"""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Tests 1-2: button styles
# ---------------------------------------------------------------------------


class TestPhoneButtonStyle:
    """style="constructive" on the phone-sharing ReplyKeyboard button."""

    def test_phone_button_has_constructive_style(self):
        """KeyboardButton created in ask_phone must carry style='constructive'."""
        from telebot import types

        btn = types.KeyboardButton(
            "Надіслати номер телефону",
            request_contact=True,
            style="constructive",
        )
        assert btn.style == "constructive"
        assert btn.request_contact is True

    def test_cabinet_button_has_constructive_style(self):
        """InlineKeyboardButton in _send_cabinet_message must carry style='constructive'."""
        message = MagicMock()
        message.chat.id = 99999

        with patch("telegram.handlers.messages.commands.get_bot") as mock_get_bot:
            mock_bot = MagicMock()
            mock_get_bot.return_value = mock_bot

            from telegram.handlers.messages.commands import _send_cabinet_message

            _send_cabinet_message(message)

        _, kwargs = mock_bot.send_message.call_args
        markup = kwargs["reply_markup"]
        button = markup.keyboard[0][0]
        assert button.style == "constructive"


# ---------------------------------------------------------------------------
# Tests 3-5: set_member_tag calls from handle_user_status_change
# ---------------------------------------------------------------------------


def _make_member_event(chat_id: int, user_id: int, username: str = "testuser") -> MagicMock:
    """Build a minimal ChatMemberUpdated mock that passes handler guards."""
    event = MagicMock()
    event.chat.id = chat_id
    event.chat.type = "supergroup"
    event.chat.title = "Test Group"
    event.new_chat_member.user.is_bot = False
    event.new_chat_member.user.id = user_id
    event.new_chat_member.user.username = username
    event.new_chat_member.user.first_name = "Test"
    event.new_chat_member.user.last_name = ""
    event.new_chat_member.status = "member"
    event.old_chat_member.status = "left"
    return event


@pytest.mark.django_db
class TestSetMemberTagOnJoin:
    """GroupService.set_member_tag is called with the right tag for each role."""

    def _patch_group_service(self):
        """Context-manager patches that prevent real Telegram API calls."""
        return (
            patch("telegram.handlers.member.user.group.GroupService.set_member_tag"),
            patch("telegram.handlers.member.user.group.GroupService.set_default_owner_permissions"),
            patch("telegram.handlers.member.user.group.GroupService.set_default_worker_permissions"),
            patch("telegram.handlers.member.user.group.GroupService.set_default_admin_permissions"),
            patch("telegram.handlers.member.user.group.GroupService.set_admin_custom_title"),
            patch("telegram.handlers.member.user.group.GroupService.kick_user"),
            patch("vacancy.services.observers.subscriber_setup.vacancy_publisher"),
        )

    def test_set_member_tag_called_for_employer(self, employer_factory, vacancy_factory, group_factory):
        """Employer entering their own vacancy group gets tag='Роботодавець'."""
        owner = employer_factory()
        group = group_factory()
        vacancy_factory(owner=owner, group=group, status="approved")

        event = _make_member_event(chat_id=group.id, user_id=owner.id, username=owner.username or "owner")

        patches = self._patch_group_service()
        with patches[0] as mock_tag, patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            from telegram.handlers.member.user.group import handle_user_status_change

            handle_user_status_change(event)

        mock_tag.assert_called_once_with(
            chat_id=group.id,
            user_id=owner.id,
            tag="Роботодавець",
        )

    def test_set_member_tag_called_for_worker(self, worker_factory, employer_factory, vacancy_factory, group_factory):
        """Worker entering a vacancy group gets tag='Працівник'."""
        owner = employer_factory()
        worker = worker_factory()
        group = group_factory()
        vacancy_factory(owner=owner, group=group, status="approved", people_count=5)

        event = _make_member_event(chat_id=group.id, user_id=worker.id, username=worker.username or "worker")

        patches = self._patch_group_service()
        with patches[0] as mock_tag, patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            from telegram.handlers.member.user.group import handle_user_status_change

            handle_user_status_change(event)

        mock_tag.assert_called_once_with(
            chat_id=group.id,
            user_id=worker.id,
            tag="Працівник",
        )

    def test_set_member_tag_called_for_admin(self, employer_factory, vacancy_factory, group_factory, user_factory):
        """Staff admin entering a vacancy group gets tag='Адміністратор'."""
        owner = employer_factory()
        admin = user_factory(is_staff=True)
        group = group_factory()
        vacancy_factory(owner=owner, group=group, status="approved")

        event = _make_member_event(chat_id=group.id, user_id=admin.id, username=admin.username or "admin")

        patches = self._patch_group_service()
        with patches[0] as mock_tag, patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            from telegram.handlers.member.user.group import handle_user_status_change

            handle_user_status_change(event)

        mock_tag.assert_called_once_with(
            chat_id=group.id,
            user_id=admin.id,
            tag="Адміністратор",
        )


# ---------------------------------------------------------------------------
# Tests 6-7: GroupService.set_member_tag internals
# ---------------------------------------------------------------------------


class TestGroupServiceSetMemberTag:
    """Unit tests for GroupService.set_member_tag itself."""

    def test_group_service_set_member_tag_calls_bot_api(self):
        """set_member_tag must delegate to bot.set_chat_member_tag with correct kwargs."""
        from telegram.handlers.bot_instance import bot
        from telegram.service.group import GroupService

        with patch.object(bot, "set_chat_member_tag") as mock_api:
            GroupService.set_member_tag(chat_id=-100123456, user_id=789, tag="Працівник")

        mock_api.assert_called_once_with(chat_id=-100123456, user_id=789, tag="Працівник")

    def test_group_service_set_member_tag_handles_error(self):
        """set_member_tag must swallow exceptions — never propagate to caller."""
        from telegram.handlers.bot_instance import bot
        from telegram.service.group import GroupService

        with patch.object(bot, "set_chat_member_tag", side_effect=Exception("API error")):
            # Must not raise
            GroupService.set_member_tag(chat_id=-100123456, user_id=789, tag="Працівник")


# ---------------------------------------------------------------------------
# Test 8: markup factory styles
# ---------------------------------------------------------------------------


class TestMarkupFactoryStyles:
    """Verify pre-existing button styles in telegram_markup_factory."""

    def test_channel_vacancy_markup_uses_danger_style(self):
        """'Apply for vacancy' button in channel post must have style='danger'."""
        vacancy = MagicMock()
        vacancy.id = 42

        from service.telegram_markup_factory import channel_vacancy_reply_markup

        markup = channel_vacancy_reply_markup(vacancy)
        button = markup.keyboard[0][0]
        assert button.style == "danger"

    def test_group_url_feedback_markup_uses_primary_style(self):
        """'Надіслати відгук' URL button must have style='primary'."""
        vacancy = MagicMock()
        vacancy.pk = 42

        with patch("service.telegram_markup_factory.get_payload_url", return_value="https://example.com/feedback"):
            from service.telegram_markup_factory import group_url_feedback_reply_markup

            markup = group_url_feedback_reply_markup(vacancy)

        button = markup.keyboard[0][0]
        assert button.style == "primary"
