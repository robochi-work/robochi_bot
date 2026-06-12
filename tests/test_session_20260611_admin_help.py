"""Регресійні тести для фічі «Допомога Адміністратора»."""

from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache

from user.models import AdminHelpRequest
from user.services.admin_help import CACHE_KEY, AdminHelpService


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_start_request_creates_pending_and_caches(worker_factory):
    user = worker_factory()
    with patch("telegram.handlers.bot_instance.bot.send_message"):
        AdminHelpService.start_request(user)
    req = AdminHelpRequest.objects.get(user=user)
    assert req.status == AdminHelpRequest.STATUS_PENDING
    assert cache.get(CACHE_KEY.format(user_id=user.id)) == req.id


@pytest.mark.django_db
def test_start_request_supersedes_previous_pending(worker_factory):
    user = worker_factory()
    with patch("telegram.handlers.bot_instance.bot.send_message"):
        AdminHelpService.start_request(user)
        AdminHelpService.start_request(user)
    assert AdminHelpRequest.objects.filter(user=user, status=AdminHelpRequest.STATUS_TIMEOUT).count() == 1
    assert AdminHelpRequest.objects.filter(user=user, status=AdminHelpRequest.STATUS_PENDING).count() == 1


@pytest.mark.django_db
def test_is_pending_returns_true_after_start(worker_factory):
    user = worker_factory()
    assert AdminHelpService.is_pending(user) is False
    with patch("telegram.handlers.bot_instance.bot.send_message"):
        AdminHelpService.start_request(user)
    assert AdminHelpService.is_pending(user) is True


@pytest.mark.django_db
def test_cancel_request_clears_cache_and_closes(worker_factory):
    user = worker_factory()
    with patch("telegram.handlers.bot_instance.bot.send_message"):
        AdminHelpService.start_request(user)
    req = AdminHelpRequest.objects.get(user=user, status=AdminHelpRequest.STATUS_PENDING)
    AdminHelpService.cancel_request(user, req.id)
    req.refresh_from_db()
    assert req.status == AdminHelpRequest.STATUS_CLOSED
    assert cache.get(CACHE_KEY.format(user_id=user.id)) is None


@pytest.mark.django_db
def test_submit_request_sends_card_to_admin_chat(worker_factory, settings):
    settings.ADMIN_HELP_CHAT_ID = -1003987159270
    user = worker_factory()
    with patch("telegram.handlers.bot_instance.bot.send_message") as mock_send:
        AdminHelpService.start_request(user)
        mock_send.reset_mock()
        sent_card = MagicMock()
        sent_card.message_id = 555
        mock_send.return_value = sent_card
        message = MagicMock()
        message.text = "Мене заблокували, не можу зайти в групу"
        message.caption = None
        message.content_type = "text"
        message.message_id = 100
        AdminHelpService.submit_request(user, message)
    req = AdminHelpRequest.objects.get(user=user)
    assert req.status == AdminHelpRequest.STATUS_OPEN
    assert req.admin_chat_message_id == 555
    assert "Мене заблокували" in req.message_text
    assert cache.get(CACHE_KEY.format(user_id=user.id)) is None
    admin_call_args = [c for c in mock_send.call_args_list if c.args and c.args[0] == -1003987159270]
    assert len(admin_call_args) == 1
    card_text = admin_call_args[0].args[1]
    assert str(user.id) in card_text
    assert "Мене заблокували" in card_text


@pytest.mark.django_db
def test_submit_without_pending_does_nothing(worker_factory, settings):
    settings.ADMIN_HELP_CHAT_ID = -1003987159270
    user = worker_factory()
    message = MagicMock()
    message.text = "test"
    message.caption = None
    message.content_type = "text"
    with patch("telegram.handlers.bot_instance.bot.send_message") as mock_send:
        AdminHelpService.submit_request(user, message)
    assert AdminHelpRequest.objects.filter(user=user).count() == 0
    mock_send.assert_not_called()


@pytest.mark.django_db
def test_close_request_marks_closed_and_sets_by(worker_factory, settings):
    settings.ADMIN_HELP_CHAT_ID = -1003987159270
    user = worker_factory()
    admin = worker_factory()
    with patch("telegram.handlers.bot_instance.bot.send_message") as mock_send:
        sent = MagicMock()
        sent.message_id = 999
        mock_send.return_value = sent
        AdminHelpService.start_request(user)
        msg = MagicMock()
        msg.text = "хелп"
        msg.caption = None
        msg.content_type = "text"
        msg.message_id = 1
        AdminHelpService.submit_request(user, msg)
    req = AdminHelpRequest.objects.get(user=user, status=AdminHelpRequest.STATUS_OPEN)
    with patch("telegram.handlers.bot_instance.bot.edit_message_text"):
        AdminHelpService.close_request(req.id, by_user=admin)
    req.refresh_from_db()
    assert req.status == AdminHelpRequest.STATUS_CLOSED
    assert req.closed_by_id == admin.id
    assert req.closed_at is not None


@pytest.mark.django_db
def test_button_label_matches_across_locales():
    from telegram.handlers.messages.global_buttons import is_admin_help_click, is_offer_click

    assert is_admin_help_click("🆘 Допомога Адміністратора") is True
    assert is_admin_help_click("🆘 Помощь администратора") is True
    assert is_offer_click("📄 Договір оферти") is True
    assert is_offer_click("📄 Договор оферты") is True
    assert is_admin_help_click("привіт як справи") is False
    assert is_offer_click("звичайне повідомлення") is False


@pytest.mark.django_db
def test_button_matches_without_emoji():
    from telegram.handlers.messages.global_buttons import is_admin_help_click, is_offer_click

    assert is_admin_help_click("Допомога Адміністратора") is True
    assert is_offer_click("Договір оферти") is True
