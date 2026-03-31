"""
Global fixtures for the robochi_bot test suite.

Strategy:
- override_settings (autouse) — replaces sensitive env values with safe test stubs
  so tests never depend on a real .env being present.
- mock_bot_api (autouse) — patches the already-created TeleBot instance so no
  real Telegram API calls are made during any test.
- Factory fixtures — thin wrappers that return the factory class; individual tests
  call them with @pytest.mark.django_db to get DB access.
"""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Settings / environment overrides
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def override_settings(settings):
    """Force safe test values for every test in the suite."""
    settings.TELEGRAM_BOT_TOKEN = "0:TestBotTokenForTestingOnly"
    settings.ADMIN_TELEGRAM_IDS = []
    settings.BASE_URL = "https://test.robochi.example"


# ---------------------------------------------------------------------------
# Telegram bot mock — prevents any real API calls
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_bot_api():
    """
    Patch all commonly used TeleBot methods on the singleton bot instance.
    New methods can be added here as the test suite grows.
    """
    from telegram.handlers.bot_instance import bot

    send_result = MagicMock(message_id=1)

    with (
        patch.object(bot, "send_message", return_value=send_result),
        patch.object(bot, "send_photo", return_value=send_result),
        patch.object(bot, "edit_message_text", return_value=send_result),
        patch.object(bot, "delete_message", return_value=True),
        patch.object(bot, "answer_callback_query", return_value=True),
        patch.object(bot, "get_webhook_info", return_value=MagicMock(url="")),
        patch.object(bot, "ban_chat_member", return_value=True),
        patch.object(bot, "unban_chat_member", return_value=True),
        patch.object(bot, "kick_chat_member", return_value=True),
    ):
        yield


# ---------------------------------------------------------------------------
# Factory fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user_factory():
    from tests.factories import UserFactory

    return UserFactory


@pytest.fixture
def employer_factory():
    from tests.factories import EmployerFactory

    return EmployerFactory


@pytest.fixture
def worker_factory():
    from tests.factories import WorkerFactory

    return WorkerFactory


@pytest.fixture
def vacancy_factory():
    from tests.factories import VacancyFactory

    return VacancyFactory


@pytest.fixture
def channel_factory():
    from tests.factories import ChannelFactory

    return ChannelFactory


@pytest.fixture
def group_factory():
    from tests.factories import GroupFactory

    return GroupFactory
