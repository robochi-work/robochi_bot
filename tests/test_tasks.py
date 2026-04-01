"""
Regression tests for Celery tasks.

These tests verify structural correctness of task functions —
no DB or real API calls needed.

The autouse mock_bot_api fixture (conftest.py) patches the bot singleton,
so imports that touch the bot instance are safe.
"""

import inspect


def test_escalate_rollcall_bot_import():
    """Regression: _escalate_rollcall must have bot imported (fix d49c40e).

    Before d49c40e the function used bot.delete_message() without importing
    bot, which caused NameError when rollcall escalation was triggered
    (i.e. after 6 unanswered reminders to the employer).
    """
    from vacancy.tasks.call import _escalate_rollcall

    source = inspect.getsource(_escalate_rollcall)

    assert "bot" in source, "_escalate_rollcall must reference bot"
    assert "from telegram.handlers.bot_instance import bot" in source, (
        "_escalate_rollcall must import bot locally before use"
    )
