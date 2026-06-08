"""Tests for apply button (Я ГОТОВИЙ ПРАЦЮВАТИ) message routing.

Session 2026-05-30 fix:
- Removed invalid `style="constructive"` from InlineKeyboardButton.

Session 2026-06-03 update:
- Owner/worker routing now uses bot.get_chat_member() to check real group membership.
- Employer-owner: in group -> card only; not in group -> invite + card.
- Worker already_in_vacancy: in group -> "Моя робота"; not in group -> group invite.
- Re-send pending join-confirm deletes old message, saves new id.
- Approval message button changed from "До поточних заявок" to "Керування вакансією".
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


def _mock_member(status="left"):
    m = MagicMock()
    m.status = status
    return m


@pytest.mark.django_db
class TestApplyButtonMessages:
    """process_start_payload routes correctly to cabinet/group messages."""

    def test_owner_not_in_group_gets_invite_and_card(self):
        """Owner NOT in Telegram group -> 2 buttons."""
        from tests.factories import EmployerFactory, GroupFactory, VacancyFactory
        from vacancy.choices import STATUS_APPROVED

        employer = EmployerFactory()
        group = GroupFactory(invite_link="https://t.me/+ownerlink123")
        vacancy = VacancyFactory(owner=employer, group=group, status=STATUS_APPROVED)

        message = _make_message(employer.id)
        payload = _encode_payload({"type": "apply", "vacancy_id": vacancy.id})

        with patch("telegram.handlers.messages.commands.get_bot") as mock_get_bot:
            mock_bot = MagicMock()
            mock_bot.get_chat_member.return_value = _mock_member("left")
            mock_get_bot.return_value = mock_bot

            from telegram.handlers.messages.commands import process_start_payload

            result = process_start_payload(payload, message)

        assert result is True
        mock_bot.send_message.assert_called_once()
        text = mock_bot.send_message.call_args.kwargs["text"]
        assert "Перейдіть у групу" in text
        markup = mock_bot.send_message.call_args.kwargs["reply_markup"]
        buttons = [row[0] for row in markup.keyboard]
        assert any(b.url == "https://t.me/+ownerlink123" for b in buttons)
        assert any(b.web_app is not None for b in buttons)

    def test_owner_in_group_gets_only_card(self):
        """Owner IS in Telegram group -> only card button."""
        from tests.factories import EmployerFactory, GroupFactory, VacancyFactory
        from vacancy.choices import STATUS_APPROVED

        employer = EmployerFactory()
        group = GroupFactory(invite_link="https://t.me/+ownerlink456")
        vacancy = VacancyFactory(owner=employer, group=group, status=STATUS_APPROVED)

        message = _make_message(employer.id)
        payload = _encode_payload({"type": "apply", "vacancy_id": vacancy.id})

        with patch("telegram.handlers.messages.commands.get_bot") as mock_get_bot:
            mock_bot = MagicMock()
            mock_bot.get_chat_member.return_value = _mock_member("administrator")
            mock_get_bot.return_value = mock_bot

            from telegram.handlers.messages.commands import process_start_payload

            result = process_start_payload(payload, message)

        assert result is True
        mock_bot.send_message.assert_called_once()
        text = mock_bot.send_message.call_args.kwargs["text"]
        assert "Перейдіть до керування" in text
        markup = mock_bot.send_message.call_args.kwargs["reply_markup"]
        buttons = [row[0] for row in markup.keyboard]
        assert len(buttons) == 1
        assert buttons[0].web_app is not None

    def test_worker_already_in_vacancy_in_group_gets_my_work(self):
        """Worker already_in_vacancy + IS in group -> 'Моя робота'."""
        from tests.factories import GroupFactory, VacancyFactory, WorkerFactory
        from vacancy.choices import STATUS_APPROVED

        worker = WorkerFactory()
        group = GroupFactory(invite_link="https://t.me/+wrkgrp")
        vacancy = VacancyFactory(group=group, status=STATUS_APPROVED)
        message = _make_message(worker.id)
        payload = _encode_payload({"type": "already_in_vacancy", "vacancy_id": vacancy.id})

        with patch("telegram.handlers.messages.commands.get_bot") as mock_get_bot:
            mock_bot = MagicMock()
            mock_bot.get_chat_member.return_value = _mock_member("member")
            mock_get_bot.return_value = mock_bot

            from telegram.handlers.messages.commands import process_start_payload

            result = process_start_payload(payload, message)

        assert result is True
        mock_bot.send_message.assert_called_once()
        text = mock_bot.send_message.call_args.kwargs["text"]
        assert "Перейдіть до своєї роботи" in text

    def test_worker_already_in_vacancy_not_in_group_gets_invite(self):
        """Worker already_in_vacancy + NOT in group -> group invite."""
        from tests.factories import GroupFactory, VacancyFactory, WorkerFactory
        from vacancy.choices import STATUS_APPROVED

        worker = WorkerFactory()
        group = GroupFactory(invite_link="https://t.me/+wrkgrp2")
        vacancy = VacancyFactory(group=group, status=STATUS_APPROVED)
        message = _make_message(worker.id)
        payload = _encode_payload({"type": "already_in_vacancy", "vacancy_id": vacancy.id})

        with patch("telegram.handlers.messages.commands.get_bot") as mock_get_bot:
            mock_bot = MagicMock()
            mock_bot.get_chat_member.return_value = _mock_member("left")
            mock_get_bot.return_value = mock_bot

            from telegram.handlers.messages.commands import process_start_payload

            result = process_start_payload(payload, message)

        assert result is True
        mock_bot.send_message.assert_called_once()
        text = mock_bot.send_message.call_args.kwargs["text"]
        assert "Перейдіть у групу" in text
        markup = mock_bot.send_message.call_args.kwargs["reply_markup"]
        button = markup.keyboard[0][0]
        assert button.url == "https://t.me/+wrkgrp2"

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
        text = mock_bot.send_message.call_args.kwargs["text"]
        assert "Перейдіть у групу" in text
        markup = mock_bot.send_message.call_args.kwargs["reply_markup"]
        button = markup.keyboard[0][0]
        assert button.url == "https://t.me/+testlink123"

    def test_no_invalid_button_style_in_inline_buttons(self):
        """Regression: InlineKeyboardButton must NOT have style='constructive'."""
        import inspect

        from telegram.handlers.messages import commands as cmd_module

        for name in (
            "_send_cabinet_message",
            "_send_employer_cabinet_message",
            "_send_admin_invite_message",
            "_send_owner_action_message",
            "_send_worker_my_work_message",
        ):
            func = getattr(cmd_module, name, None)
            assert func is not None, f"{name} must exist"
            source = inspect.getsource(func)
            assert 'style="constructive"' not in source, f"{name} has style=constructive"
            assert "style='constructive'" not in source, f"{name} has style=constructive"


@pytest.mark.django_db
class TestPendingConfirmAntispam:
    """Re-send pending confirm deletes old message and updates confirm_msg_ids."""

    def test_repeat_apply_deletes_old_confirm_and_saves_new_id(self):
        from telegram.choices import CallStatus, CallType
        from telegram.models import Status
        from tests.factories import GroupFactory, VacancyFactory, WorkerFactory
        from vacancy.choices import STATUS_APPROVED
        from vacancy.models import VacancyUser, VacancyUserCall

        worker = WorkerFactory()
        group = GroupFactory(invite_link="https://t.me/+grp")
        vacancy = VacancyFactory(group=group, status=STATUS_APPROVED)
        vacancy.extra = {"confirm_msg_ids": {str(worker.id): 100}}
        vacancy.save(update_fields=["extra"])

        VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.PENDING_CONFIRM.value)
        VacancyUserCall.objects.create(
            vacancy_user=VacancyUser.objects.get(user=worker, vacancy=vacancy),
            call_type=CallType.WORKER_JOIN_CONFIRM.value,
            status=CallStatus.SENT.value,
        )

        message = _make_message(worker.id)
        payload = _encode_payload({"type": "apply", "vacancy_id": vacancy.id})

        with patch("telegram.handlers.messages.commands.get_bot") as mock_get_bot:
            mock_bot = MagicMock()
            mock_bot.send_message.return_value.message_id = 200
            mock_get_bot.return_value = mock_bot

            from telegram.handlers.messages.commands import process_start_payload

            result = process_start_payload(payload, message)

        assert result is True
        mock_bot.delete_message.assert_called_once_with(chat_id=worker.id, message_id=100)
        mock_bot.send_message.assert_called_once()

        vacancy.refresh_from_db()
        assert vacancy.extra["confirm_msg_ids"][str(worker.id)] == 200
