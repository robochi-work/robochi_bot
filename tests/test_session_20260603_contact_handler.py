"""Integration tests for contact handler — Ukrainian-only filter."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def fake_message():
    msg = MagicMock()
    msg.chat.id = 999
    msg.message_id = 1
    msg.from_user.id = 999
    return msg


@pytest.fixture
def fake_user():
    user = MagicMock()
    user.id = 42
    user.phone_number = ""
    return user


def _call_inner(fake_message, fake_user):
    """Bypass @user_required decorator and call the raw handler."""
    from telegram.handlers.contact.user_phone_number import contact

    inner = contact.__wrapped__
    inner(fake_message, fake_user)


class TestContactHandlerNonUA:
    """Non-+380 contact must be rejected with no DB writes and no UI."""

    def test_russian_number_rejected(self, fake_message, fake_user):
        fake_message.contact = MagicMock()
        fake_message.contact.phone_number = "79161234567"

        with (
            patch("telegram.handlers.contact.user_phone_number.bot") as mock_bot,
            patch("telegram.handlers.contact.user_phone_number.AuthIdentity") as mock_auth,
            patch("telegram.utils.notify_admins_new_user") as mock_notify,
        ):
            _call_inner(fake_message, fake_user)

            # phone NOT saved
            fake_user.save.assert_not_called()
            # auth identity NOT created
            mock_auth.objects.get_or_create.assert_not_called()
            # admin NOT notified
            mock_notify.assert_not_called()
            # menu button NOT set
            mock_bot.set_chat_menu_button.assert_not_called()
            # rejection message sent with correct text
            assert mock_bot.send_message.called
            call_kwargs = mock_bot.send_message.call_args.kwargs
            sent_text = call_kwargs.get("text", "")
            assert "Україн" in sent_text

    def test_polish_number_rejected(self, fake_message, fake_user):
        fake_message.contact = MagicMock()
        fake_message.contact.phone_number = "48571234567"

        with (
            patch("telegram.handlers.contact.user_phone_number.bot") as mock_bot,
            patch("telegram.handlers.contact.user_phone_number.AuthIdentity") as mock_auth,
            patch("telegram.utils.notify_admins_new_user"),
        ):
            _call_inner(fake_message, fake_user)

            fake_user.save.assert_not_called()
            mock_auth.objects.get_or_create.assert_not_called()
            mock_bot.set_chat_menu_button.assert_not_called()

    def test_usa_number_rejected(self, fake_message, fake_user):
        fake_message.contact = MagicMock()
        fake_message.contact.phone_number = "12025551234"

        with (
            patch("telegram.handlers.contact.user_phone_number.bot") as mock_bot,
            patch("telegram.handlers.contact.user_phone_number.AuthIdentity") as mock_auth,
            patch("telegram.utils.notify_admins_new_user"),
        ):
            _call_inner(fake_message, fake_user)

            fake_user.save.assert_not_called()
            mock_auth.objects.get_or_create.assert_not_called()
            mock_bot.set_chat_menu_button.assert_not_called()


class TestContactHandlerUA:
    """+380 contact must pass through normal flow."""

    def test_ukrainian_number_accepted(self, fake_message, fake_user):
        fake_message.contact = MagicMock()
        fake_message.contact.phone_number = "380671234567"
        fake_user.work_profile.is_completed = False

        with (
            patch("telegram.handlers.contact.user_phone_number.bot") as mock_bot,
            patch("telegram.handlers.contact.user_phone_number.AuthIdentity") as mock_auth,
            patch("telegram.utils.notify_admins_new_user") as mock_notify,
            patch("telegram.handlers.contact.user_phone_number.reverse", return_value="/check/"),
            patch("telegram.handlers.contact.user_phone_number.settings") as mock_settings,
        ):
            mock_settings.BASE_URL = "https://robochi.pp.ua"

            _call_inner(fake_message, fake_user)

            # phone saved
            fake_user.save.assert_called_once_with(update_fields=["phone_number"])
            assert fake_user.phone_number == "+380671234567"
            # auth identity created
            mock_auth.objects.get_or_create.assert_called_once()
            # admin notified
            mock_notify.assert_called_once()
            # menu button set
            mock_bot.set_chat_menu_button.assert_called_once()

    def test_ukrainian_number_with_plus_accepted(self, fake_message, fake_user):
        fake_message.contact = MagicMock()
        fake_message.contact.phone_number = "+380501112233"
        fake_user.work_profile.is_completed = False

        with (
            patch("telegram.handlers.contact.user_phone_number.bot") as mock_bot,
            patch("telegram.handlers.contact.user_phone_number.AuthIdentity"),
            patch("telegram.utils.notify_admins_new_user"),
            patch("telegram.handlers.contact.user_phone_number.reverse", return_value="/check/"),
            patch("telegram.handlers.contact.user_phone_number.settings") as mock_settings,
        ):
            mock_settings.BASE_URL = "https://robochi.pp.ua"

            _call_inner(fake_message, fake_user)

            fake_user.save.assert_called_once()
            assert fake_user.phone_number == "+380501112233"
            mock_bot.set_chat_menu_button.assert_called_once()
