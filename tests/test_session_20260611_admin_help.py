"""Регресійні тести для фічі «Допомога Адміністратора»."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.utils import timezone

from user.models import AdminHelpRequest
from user.services.admin_help import CACHE_KEY, COOLDOWN_KEY, AdminHelpService


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
        # Между вызовами очищаем cooldown — иначе второй start_request будет отбит rate-limit'ом
        cache.delete(COOLDOWN_KEY.format(user_id=user.id))
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


@pytest.mark.django_db
def test_cooldown_blocks_repeat_within_5_minutes(worker_factory):
    """Повторне натискання у межах 5 хв НЕ створює новий запит."""
    user = worker_factory()
    with patch("telegram.handlers.bot_instance.bot.send_message"):
        AdminHelpService.start_request(user)
        # Друге натискання — cooldown активний, новий request не створюється
        AdminHelpService.start_request(user)
    # Має бути рівно 1 запит (другий заблокувався cooldown'ом)
    assert AdminHelpRequest.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_cooldown_sends_warning_message_on_repeat(worker_factory):
    """При повторному натисканні в межах 5 хв юзер отримує попередження."""
    user = worker_factory()
    sent_texts = []

    def fake_send(uid, text, **kw):
        sent_texts.append(text)
        m = MagicMock()
        m.message_id = 1
        return m

    with patch("telegram.handlers.bot_instance.bot.send_message", side_effect=fake_send):
        AdminHelpService.start_request(user)
        AdminHelpService.start_request(user)  # повтор у межах cooldown

    # Друге повідомлення має містити попередження
    assert any("зверталися до Адміністратора" in t for t in sent_texts), sent_texts


@pytest.mark.django_db
def test_cleanup_stale_pending_marks_timeout(worker_factory, settings):
    """Celery-таска cleanup_stale_admin_help: pending → timeout + видалення повідомлення."""
    from user.tasks import cleanup_stale_admin_help_task

    settings.ADMIN_HELP_CHAT_ID = -1003987159270
    user = worker_factory()

    with patch("telegram.handlers.bot_instance.bot.send_message") as mock_send:
        sent = MagicMock()
        sent.message_id = 777
        mock_send.return_value = sent
        AdminHelpService.start_request(user)

    req = AdminHelpRequest.objects.get(user=user)
    assert req.status == AdminHelpRequest.STATUS_PENDING

    with patch("telegram.handlers.bot_instance.bot.delete_message") as mock_del:
        cleanup_stale_admin_help_task(req.id)
        mock_del.assert_called_once_with(user.id, 777)

    req.refresh_from_db()
    assert req.status == AdminHelpRequest.STATUS_TIMEOUT
    assert req.closed_at is not None
    # Cache для pending має бути очищений
    assert cache.get(CACHE_KEY.format(user_id=user.id)) is None


@pytest.mark.django_db
def test_cleanup_stale_skips_already_submitted(worker_factory, settings):
    """Якщо юзер встиг відправити повідомлення (OPEN) — таска нічого не робить."""
    from user.tasks import cleanup_stale_admin_help_task

    settings.ADMIN_HELP_CHAT_ID = -1003987159270
    user = worker_factory()

    with patch("telegram.handlers.bot_instance.bot.send_message") as mock_send:
        sent = MagicMock()
        sent.message_id = 888
        mock_send.return_value = sent
        AdminHelpService.start_request(user)
        msg = MagicMock()
        msg.text = "вже надіслав"
        msg.caption = None
        msg.content_type = "text"
        msg.message_id = 5
        AdminHelpService.submit_request(user, msg)

    req = AdminHelpRequest.objects.get(user=user, status=AdminHelpRequest.STATUS_OPEN)
    cleanup_stale_admin_help_task(req.id)
    req.refresh_from_db()
    assert req.status == AdminHelpRequest.STATUS_OPEN


@pytest.mark.django_db
def test_auto_close_closes_open_requests_older_than_24h(worker_factory):
    """auto_close_admin_help_task: OPEN > 24h → CLOSED."""
    from user.tasks import auto_close_admin_help_task

    user = worker_factory()
    old_req = AdminHelpRequest.objects.create(user=user, status=AdminHelpRequest.STATUS_OPEN)
    fresh_req = AdminHelpRequest.objects.create(user=user, status=AdminHelpRequest.STATUS_OPEN)

    # Зсуваємо created_at старого назад на 25 годин (auto_now_add не редагується напряму → через update)
    AdminHelpRequest.objects.filter(id=old_req.id).update(created_at=timezone.now() - timedelta(hours=25))

    auto_close_admin_help_task()

    old_req.refresh_from_db()
    fresh_req.refresh_from_db()
    assert old_req.status == AdminHelpRequest.STATUS_CLOSED
    assert old_req.closed_at is not None
    assert fresh_req.status == AdminHelpRequest.STATUS_OPEN  # свіжий не чіпаємо
