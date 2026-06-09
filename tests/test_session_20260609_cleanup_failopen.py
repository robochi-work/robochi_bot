"""Regression test for the cleanup bug that deleted live users
(@Nephrite_u on 31.05, @ParaibaUA on 08.06).

Root cause: check_telegram_deleted returned True on ANY API exception
(rate limit, timeout, network) -> cleanup_inactive_users deleted live users
-> Vacancy.owner CASCADE wiped their vacancies too.

Fix: on exception, return False (fail-open). Live users stay live.
"""

from unittest.mock import patch


def test_check_telegram_deleted_returns_false_on_api_exception():
    """When bot.get_chat raises ANY exception, we MUST NOT mark user as deleted."""
    from user.tasks import check_telegram_deleted

    with patch("user.tasks.bot.get_chat", side_effect=ConnectionError("rate limit")):
        result = check_telegram_deleted(8872955591)
        assert result is False, "fail-open: API errors must NOT delete the user"


def test_check_telegram_deleted_returns_false_on_timeout():
    from user.tasks import check_telegram_deleted

    with patch("user.tasks.bot.get_chat", side_effect=TimeoutError("read timeout")):
        result = check_telegram_deleted(1689560498)
        assert result is False


def test_check_telegram_deleted_returns_true_on_deleted_account_first_name():
    """Real deleted Telegram accounts have empty or 'Deleted Account' first_name."""
    from unittest.mock import MagicMock

    from user.tasks import check_telegram_deleted

    fake_chat = MagicMock()
    fake_chat.first_name = "Deleted Account"
    with patch("user.tasks.bot.get_chat", return_value=fake_chat):
        assert check_telegram_deleted(123) is True


def test_check_telegram_deleted_returns_true_on_empty_first_name():
    from unittest.mock import MagicMock

    from user.tasks import check_telegram_deleted

    fake_chat = MagicMock()
    fake_chat.first_name = ""
    with patch("user.tasks.bot.get_chat", return_value=fake_chat):
        assert check_telegram_deleted(123) is True


def test_check_telegram_deleted_returns_false_for_live_user():
    from unittest.mock import MagicMock

    from user.tasks import check_telegram_deleted

    fake_chat = MagicMock()
    fake_chat.first_name = "Стройсервис"
    with patch("user.tasks.bot.get_chat", return_value=fake_chat):
        assert check_telegram_deleted(8872955591) is False
