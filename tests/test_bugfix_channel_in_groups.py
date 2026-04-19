"""
Regression test: auto_approve and handle_user_status_change must NOT create
Group records when Telegram sends events for channels (chat.type="channel").

Bug: handlers in telegram/handlers/member/user/group.py called
     Group.objects.update_or_create(id=req.chat.id, ...) without checking
     chat.type, so channel IDs leaked into the Group table.

Fix: added `if req.chat.type != "supergroup": return` guards at the top of
     both handlers (before any DB access).
"""

from unittest.mock import MagicMock, patch

import pytest

from telegram.models import Group

CHANNEL_ID = -100999


def _make_channel_chat():
    chat = MagicMock()
    chat.id = CHANNEL_ID
    chat.type = "channel"
    chat.title = "Test Channel"
    return chat


def _make_chat_join_request():
    """Fake ChatJoinRequest with chat.type='channel'."""
    req = MagicMock()
    req.chat = _make_channel_chat()
    req.from_user = MagicMock()
    req.from_user.id = 123456789
    req.from_user.username = "testworker"
    return req


def _make_chat_member_updated():
    """Fake ChatMemberUpdated event with chat.type='channel'."""
    event = MagicMock()
    event.chat = _make_channel_chat()

    event.new_chat_member = MagicMock()
    event.new_chat_member.user = MagicMock()
    event.new_chat_member.user.id = 123456789
    event.new_chat_member.user.username = "testworker"
    event.new_chat_member.user.is_bot = False
    event.new_chat_member.status = "member"

    event.old_chat_member = MagicMock()
    event.old_chat_member.status = "left"

    return event


@pytest.mark.django_db
def test_auto_approve_does_not_create_group_for_channel():
    """auto_approve must return early for chat.type='channel' without touching DB."""
    from telegram.handlers.member.user.group import auto_approve

    req = _make_chat_join_request()

    with patch("telegram.handlers.member.user.group.bot"):
        auto_approve(req)

    assert not Group.objects.filter(id=CHANNEL_ID).exists()


@pytest.mark.django_db
def test_handle_user_status_change_does_not_create_group_for_channel():
    """handle_user_status_change must return early for chat.type='channel' without touching DB."""
    from telegram.handlers.member.user.group import handle_user_status_change

    event = _make_chat_member_updated()

    with patch("telegram.handlers.member.user.group.bot"):
        handle_user_status_change(event)

    assert not Group.objects.filter(id=CHANNEL_ID).exists()
