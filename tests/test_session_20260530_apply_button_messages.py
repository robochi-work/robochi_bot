"""Tests for apply button (Я ГОТОВИЙ ПРАЦЮВАТИ) message routing.

Session 2026-05-30 fix:
- Removed invalid `style="constructive"` from InlineKeyboardButton.

Session 2026-06-03 update:
- Employer-owner pressing own vacancy -> _send_owner_action_message:
    * no employer_invite_msg_id -> 2 buttons (group invite + vacancy card), id saved
    * has employer_invite_msg_id -> 1 button (vacancy card only)
- already_in_vacancy (worker repeat press) -> _send_worker_my_work_message
  (redirect to "Моя робота" page in personal cabinet)
- Re-send pending join-confirm now deletes old message and overwrites confirm_msg_ids.
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
    """process_start_payload routes correctly to cabinet/group messages."""

    def test_owner_with_no_invite_gets_group_and_card_buttons(self):
        """type=apply + role=employer + owner + no employer_invite_msg_id ->
        message with 2 buttons (group invite + card), and id is saved to extra."""
        from tests.factories import EmployerFactory, GroupFactory, VacancyFactory
        from vacancy.choices import STATUS_APPROVED

        employer = EmployerFactory()
        group = GroupFactory(invite_link="https://t.me/+ownerlink123")
        vacancy = VacancyFactory(owner=employer, group=group, status=STATUS_APPROVED)
        vacancy.extra = {}
        vacancy.save(update_fields=["extra"])

        message = _make_message(employer.id)
        payload = _encode_payload({"type": "apply", "vacancy_id": vacancy.id})

        with patch("telegram.handlers.messages.commands.get_bot") as mock_get_bot:
            mock_bot = MagicMock()
            mock_bot.send_message.return_value.message_id = 555
            mock_get_bot.return_value = mock_bot

            from telegram.handlers.messages.commands import process_start_payload

            result = process_start_payload(payload, message)

        assert result is True
        mock_bot.send_message.assert_called_once()
        sent_text = mock_bot.send_message.call_args.kwargs["text"]
        assert "Це Ваша вакансія" in sent_text
        markup = mock_bot.send_message.call_args.kwargs["reply_markup"]
        buttons = [row[0] for row in markup.keyboard]
        assert any(b.url == "https://t.me/+ownerlink123" for b in buttons), "group invite button missing"
        assert any(b.web_app is not None for b in buttons), "vacancy card WebApp button missing"

        vacancy.refresh_from_db()
        assert vacancy.extra.get("employer_invite_msg_id") == 555

    def test_owner_with_invite_already_sent_gets_only_card_button(self):
        """type=apply + role=employer + owner + employer_invite_msg_id present ->
        only card button (assumed already in group)."""
        from tests.factories import EmployerFactory, GroupFactory, VacancyFactory
        from vacancy.choices import STATUS_APPROVED

        employer = EmployerFactory()
        group = GroupFactory(invite_link="https://t.me/+ownerlink456")
        vacancy = VacancyFactory(owner=employer, group=group, status=STATUS_APPROVED)
        vacancy.extra = {"employer_invite_msg_id": 42}
        vacancy.save(update_fields=["extra"])

        message = _make_message(employer.id)
        payload = _encode_payload({"type": "apply", "vacancy_id": vacancy.id})

        with patch("telegram.handlers.messages.commands.get_bot") as mock_get_bot:
            mock_bot = MagicMock()
            mock_bot.send_message.return_value.message_id = 777
            mock_get_bot.return_value = mock_bot

            from telegram.handlers.messages.commands import process_start_payload

            result = process_start_payload(payload, message)

        assert result is True
        mock_bot.send_message.assert_called_once()
        sent_text = mock_bot.send_message.call_args.kwargs["text"]
        assert "Перейдіть до керування" in sent_text
        markup = mock_bot.send_message.call_args.kwargs["reply_markup"]
        buttons = [row[0] for row in markup.keyboard]
        assert len(buttons) == 1, f"expected 1 button, got {len(buttons)}"
        assert buttons[0].web_app is not None, "single button must be WebApp card"
        assert not any(b.url == "https://t.me/+ownerlink456" for b in buttons)

        vacancy.refresh_from_db()
        # id stays as it was — should NOT be overwritten
        assert vacancy.extra.get("employer_invite_msg_id") == 42

    def test_already_in_vacancy_gets_my_work_redirect(self):
        """type=already_in_vacancy (worker) -> message about going to 'Моя робота'."""
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
        assert "Перейдіть до своєї роботи" in sent_text
        markup = mock_bot.send_message.call_args.kwargs["reply_markup"]
        buttons = [row[0] for row in markup.keyboard]
        assert len(buttons) == 1
        assert buttons[0].web_app is not None
        assert "/work/my-work/" in buttons[0].web_app.url

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
    """Worker pressed apply twice while old join-confirm message still pending —
    old message must be deleted before sending new one, and confirm_msg_ids must be updated."""

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

        vu = VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.PENDING_CONFIRM.value)
        VacancyUserCall.objects.create(
            vacancy_user=vu,
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
