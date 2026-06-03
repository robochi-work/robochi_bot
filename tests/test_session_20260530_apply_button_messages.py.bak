"""Tests for apply button (Я ГОТОВИЙ ПРАЦЮВАТИ) message routing.

Session 2026-05-30 fix:
- Removed invalid `style="constructive"` from InlineKeyboardButton (Telegram API rejects it).
- Verified deep-link payload routing for 3 cases:
  * type=apply + employer role -> _send_employer_cabinet_message
  * type=already_in_vacancy -> _send_cabinet_message
  * type=admin_apply -> _send_admin_invite_message (group invite link)
"""

import base64
import json
from unittest.mock import MagicMock, patch

import pytest


def _encode_payload(data: dict) -> str:
    json_str = json.dumps(data, separators=(",", ":"))
    return base64.urlsafe_b64encode(json_str.encode()).decode().rstrip("=")


def _make_message(user_id: int):
    msg = MagicMock()
    msg.from_user.id = user_id
    msg.chat.id = user_id
    return msg


@pytest.mark.django_db
class TestApplyButtonMessages:
    """process_start_payload routes correctly to 3 different cabinet messages."""

    def test_employer_gets_employer_cabinet_text(self):
        """type=apply + role=employer -> message about 'керувати вакансією'."""
        from tests.factories import EmployerFactory

        employer = EmployerFactory()
        message = _make_message(employer.id)
        payload = _encode_payload({"type": "apply", "vacancy_id": 999})

        with patch("telegram.handlers.messages.commands.get_bot") as mock_get_bot:
            mock_bot = MagicMock()
            mock_get_bot.return_value = mock_bot

            from telegram.handlers.messages.commands import process_start_payload

            result = process_start_payload(payload, message)

        assert result is True
        mock_bot.send_message.assert_called_once()
        sent_text = mock_bot.send_message.call_args.kwargs["text"]
        assert "керувати вакансією" in sent_text

    def test_already_in_vacancy_gets_worker_cabinet_text(self):
        """type=already_in_vacancy -> message about 'обрати роботу'."""
        from tests.factories import WorkerFactory

        worker = WorkerFactory()
        message = _make_message(worker.id)
        payload = _encode_payload({"type": "already_in_vacancy", "vacancy_id": 999})

        with patch("telegram.handlers.messages.commands.get_bot") as mock_get_bot:
            mock_bot = MagicMock()
            mock_get_bot.return_value = mock_bot

            from telegram.handlers.messages.commands import process_start_payload

            result = process_start_payload(payload, message)

        assert result is True
        mock_bot.send_message.assert_called_once()
        sent_text = mock_bot.send_message.call_args.kwargs["text"]
        assert "обрати роботу" in sent_text

    def test_admin_apply_gets_group_invite_link(self):
        """type=admin_apply -> message with group invite link button."""
        from tests.factories import GroupFactory, UserFactory, VacancyFactory

        admin = UserFactory(is_staff=True)
        group = GroupFactory(invite_link="https://t.me/+testlink123")
        vacancy = VacancyFactory(group=group)
        message = _make_message(admin.id)
        payload = _encode_payload({"type": "admin_apply", "vacancy_id": vacancy.id})

        with patch("telegram.handlers.messages.commands.get_bot") as mock_get_bot:
            mock_bot = MagicMock()
            mock_get_bot.return_value = mock_bot

            from telegram.handlers.messages.commands import process_start_payload

            result = process_start_payload(payload, message)

        assert result is True
        mock_bot.send_message.assert_called_once()
        sent_text = mock_bot.send_message.call_args.kwargs["text"]
        assert "Перейдіть у групу" in sent_text
        markup = mock_bot.send_message.call_args.kwargs["reply_markup"]
        button = markup.keyboard[0][0]
        assert button.url == "https://t.me/+testlink123"

    def test_no_invalid_button_style_in_inline_buttons(self):
        """Regression: InlineKeyboardButton must NOT have style='constructive'.

        Telegram API rejects this parameter with:
            Bad Request: can't parse inline keyboard button: invalid button style specified
        """
        import inspect

        from telegram.handlers.messages import commands as cmd_module

        for name in (
            "_send_cabinet_message",
            "_send_employer_cabinet_message",
            "_send_admin_invite_message",
        ):
            func = getattr(cmd_module, name, None)
            assert func is not None, f"{name} must exist"
            source = inspect.getsource(func)
            assert 'style="constructive"' not in source, (
                f"{name} contains invalid Telegram API parameter style=constructive"
            )
            assert "style='constructive'" not in source, (
                f"{name} contains invalid Telegram API parameter style=constructive"
            )
