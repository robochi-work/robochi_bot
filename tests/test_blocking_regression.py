"""
Regression tests for blocking system changes (April 2026).

Covers:
1.  admin_search_users annotates active_block_type on each user
2.  admin_search_vacancies annotates active_block_id and active_block_type
3.  admin_block_user view does NOT set is_active=False directly (only BlockService)
4.  admin_block_user unblock does NOT set is_active=True directly (only BlockService)
5.  Worker dashboard: «Мої вакансії» button is ACTIVE on temporary block
6.  Worker dashboard: «Мої вакансії» button is DISABLED on permanent block
7.  auto_approve: declines unregistered user (no work_profile)
8.  auto_approve: declines employer trying to join a foreign vacancy group
9.  VacancyStartCallFailObserver: creates block with reason=employer_uncheck
10. VacancyAfterStartCallFailObserver: only queries AFTER_START call type, not START
11. vacancy_reinvite_worker: removes active block and sends bot message
"""

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse

from tests.factories import (
    ChannelFactory,
    EmployerFactory,
    GroupFactory,
    UserFactory,
    VacancyFactory,
    WorkerFactory,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_join_request(user_id: int, chat_id: int, username: str = "testuser") -> MagicMock:
    """Build a minimal fake ChatJoinRequest accepted by auto_approve."""
    req = MagicMock()
    req.from_user.id = user_id
    req.from_user.username = username
    req.chat.id = chat_id
    req.chat.type = "supergroup"
    req.chat.title = "Test Group"
    return req


def _create_active_vacancy(owner, group, channel):
    """Create an approved vacancy via factory; override owner/group/channel."""
    v = VacancyFactory(owner=owner, group=group, channel=channel, status="approved")
    return v


# ---------------------------------------------------------------------------
# 1. admin_search_users annotates active_block_type
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_search_users_has_block_type(client):
    """admin_search_users must set active_block_type on every user in the list."""
    from user.choices import BlockType
    from user.services import BlockService

    admin = UserFactory(is_staff=True)
    target = WorkerFactory()
    block = BlockService.block_user(target, block_type=BlockType.TEMPORARY)

    client.force_login(admin)
    url = reverse("work:admin_search_users")
    response = client.get(url, {"q": target.username})

    assert response.status_code == 200
    users = response.context["users"]
    annotated = next((u for u in users if u.pk == target.pk), None)
    assert annotated is not None, "Target user not in search results"
    assert annotated.active_block_id == block.pk
    assert annotated.active_block_type == BlockType.TEMPORARY


# ---------------------------------------------------------------------------
# 2. admin_search_vacancies annotates active_block_id / active_block_type
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_search_vacancies_has_block_type(client):
    """admin_search_vacancies must annotate active_block_id and active_block_type."""
    from user.choices import BlockType
    from user.services import BlockService

    admin = UserFactory(is_staff=True)
    employer = EmployerFactory()
    block = BlockService.block_user(employer, block_type=BlockType.PERMANENT)

    client.force_login(admin)
    url = reverse("work:admin_search_vacancies")
    response = client.get(url)

    assert response.status_code == 200
    users = response.context["users"]
    annotated = next((u for u in users if u.pk == employer.pk), None)
    assert annotated is not None, "Employer not in vacancy search results"
    assert annotated.active_block_id == block.pk
    assert annotated.active_block_type == BlockType.PERMANENT


# ---------------------------------------------------------------------------
# 3. admin_block_user view does NOT duplicate is_active=False
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_permanent_block_does_not_set_is_active_false_in_view(client):
    """The view must delegate is_active management to BlockService exclusively.

    When BlockService.block_user is mocked (does nothing), the view must NOT
    directly set user.is_active=False on its own.
    """
    from user.models import UserBlock
    from user.services import BlockService

    admin = UserFactory(is_staff=True)
    target = UserFactory()
    client.force_login(admin)

    fake_block = MagicMock()
    fake_block.get_reason_display.return_value = "manual"

    # Patch the class method directly — works regardless of lazy import in view
    with patch.object(BlockService, "block_user", return_value=fake_block) as mock_block:
        url = reverse("work:admin_block_user", kwargs={"user_id": target.pk})
        client.post(url, {"action": "block", "block_type": "permanent", "reason": "manual"})

    mock_block.assert_called_once()
    # BlockService was mocked → is_active NOT changed. If the view also set it
    # directly, this assertion would fail.
    target.refresh_from_db()
    assert target.is_active is True, "View must not set is_active=False itself"
    # No real UserBlock was created by the view itself
    assert UserBlock.objects.filter(user=target).count() == 0


# ---------------------------------------------------------------------------
# 4. admin_block_user unblock does NOT duplicate is_active=True
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unblock_does_not_duplicate_is_active_true(client):
    """The view must delegate is_active restoration to BlockService exclusively.

    When BlockService.unblock_user is mocked, the view must NOT directly set
    user.is_active=True on its own.
    """
    from user.choices import BlockType
    from user.services import BlockService

    admin = UserFactory(is_staff=True)
    target = UserFactory()
    block = BlockService.block_user(target, block_type=BlockType.PERMANENT)
    target.refresh_from_db()
    assert target.is_active is False  # BlockService set it

    client.force_login(admin)

    with patch.object(BlockService, "unblock_user") as mock_unblock:
        url = reverse("work:admin_block_user", kwargs={"user_id": target.pk})
        client.post(url, {"action": "unblock", "block_id": str(block.pk)})

    mock_unblock.assert_called_once_with(block.pk)
    # BlockService.unblock_user was mocked → is_active stays False.
    # If the view also set it directly, it would be True now.
    target.refresh_from_db()
    assert target.is_active is False, "View must not set is_active=True itself"


# ---------------------------------------------------------------------------
# 5. Worker dashboard button ACTIVE on temporary block
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_worker_dashboard_button_active_on_temporary_block(client):
    """«Мої вакансії» link must NOT be disabled when block is temporary."""
    from city.models import City
    from user.choices import BlockType
    from user.services import BlockService

    city = City.objects.create(name="BlockTestCity5")
    ChannelFactory(city=city)

    worker = WorkerFactory(phone_number="+380991111111")
    worker.work_profile.city = city
    worker.work_profile.save()

    BlockService.block_user(worker, block_type=BlockType.TEMPORARY)

    client.force_login(worker)
    response = client.get(reverse("index"))

    assert response.status_code == 200
    content = response.content.decode()
    # Temporary block → normal link rendered (button must NOT have disabled class)
    assert 'class="worker-btn disabled"' not in content


# ---------------------------------------------------------------------------
# 6. Worker dashboard button DISABLED on permanent block
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_worker_dashboard_button_disabled_on_permanent_block():
    """«Мої вакансії» link must have «disabled» class when block is permanent.

    Permanent block sets is_active=False, so the user can't be loaded from the
    session by Django's default backend. We bypass this by rendering the template
    directly with a crafted context — the goal is to verify the template logic,
    not the auth pipeline.
    """
    from django.template.loader import render_to_string
    from django.test import RequestFactory

    from city.models import City
    from user.choices import BlockType
    from user.services import BlockService

    city = City.objects.create(name="BlockTestCity6")
    channel = ChannelFactory(city=city)

    worker = WorkerFactory(phone_number="+380992222222")
    worker.work_profile.city = city
    worker.work_profile.save()

    active_block = BlockService.block_user(worker, block_type=BlockType.PERMANENT)

    context = {
        "work_profile": worker.work_profile,
        "channel": channel,
        "current_vacancy": None,
        "reviews_count": 0,
        "is_blocked": True,
        "active_block": active_block,
    }
    request = RequestFactory().get("/")
    request.user = worker
    content = render_to_string("work/worker_dashboard.html", context, request=request)

    assert 'class="worker-btn disabled"' in content


# ---------------------------------------------------------------------------
# 7. auto_approve rejects unregistered user (no work_profile)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_auto_approve_rejects_unregistered_user():
    """User with no work_profile must be declined in auto_approve."""
    from telegram.handlers.bot_instance import bot
    from telegram.handlers.member.user.group import auto_approve

    # Bare user: no work_profile created (plain UserFactory, not Worker/EmployerFactory)
    bare_user = UserFactory()
    chat_id = -1_009_000_001

    req = _make_join_request(user_id=bare_user.id, chat_id=chat_id)

    with (
        patch.object(bot, "decline_chat_join_request") as mock_decline,
        patch.object(bot, "approve_chat_join_request") as mock_approve,
    ):
        auto_approve(req)

    mock_decline.assert_called_once_with(chat_id, bare_user.id)
    mock_approve.assert_not_called()


# ---------------------------------------------------------------------------
# 8. auto_approve rejects employer trying to join a foreign vacancy group
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_auto_approve_rejects_employer_in_foreign_group():
    """Employer who is NOT the vacancy owner must be declined."""
    from telegram.handlers.bot_instance import bot
    from telegram.handlers.member.user.group import auto_approve
    from telegram.models import Group

    employer = EmployerFactory()
    other_owner = EmployerFactory()

    chat_id = -1_009_000_002
    group = Group.objects.create(id=chat_id, title="Foreign Group", is_active=True)
    channel = ChannelFactory()

    # Use the factory to avoid NOT NULL constraint issues
    VacancyFactory(owner=other_owner, group=group, channel=channel, status="approved")

    req = _make_join_request(user_id=employer.id, chat_id=chat_id)

    with (
        patch.object(bot, "decline_chat_join_request") as mock_decline,
        patch.object(bot, "approve_chat_join_request") as mock_approve,
    ):
        auto_approve(req)

    mock_decline.assert_called_once_with(chat_id, employer.id)
    mock_approve.assert_not_called()


# ---------------------------------------------------------------------------
# 9. VacancyStartCallFailObserver creates block with reason=employer_uncheck
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_start_call_fail_uses_employer_uncheck_reason():
    """VacancyStartCallFailObserver must block rejected workers with reason=employer_uncheck."""
    from telegram.choices import CallStatus, CallType, Status
    from user.choices import BlockReason
    from user.models import UserBlock
    from vacancy.models import VacancyUser, VacancyUserCall
    from vacancy.services.observers.call_observer import VacancyStartCallFailObserver

    employer = EmployerFactory()
    worker = WorkerFactory()
    group = GroupFactory(status="process")
    channel = ChannelFactory()
    vacancy = _create_active_vacancy(employer, group, channel)

    vacancy_user = VacancyUser.objects.create(
        user=worker,
        vacancy=vacancy,
        status=Status.MEMBER,
    )
    VacancyUserCall.objects.create(
        vacancy_user=vacancy_user,
        call_type=CallType.START,
        status=CallStatus.REJECT,
    )

    notifier = MagicMock()
    with patch("vacancy.services.observers.call_observer.GroupService.kick_user"):
        VacancyStartCallFailObserver(notifier=notifier).update("event", {"vacancy": vacancy})

    blocks = UserBlock.objects.filter(user=worker, is_active=True)
    assert blocks.exists(), "Worker should be blocked after start-call fail"
    assert blocks.first().reason == BlockReason.EMPLOYER_UNCHECK


# ---------------------------------------------------------------------------
# 10. VacancyAfterStartCallFailObserver filters by AFTER_START (not START)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_after_start_call_fail_filters_after_start_type():
    """VacancyAfterStartCallFailObserver must only block AFTER_START rejects, not START."""
    from telegram.choices import CallStatus, CallType, Status
    from user.models import UserBlock
    from vacancy.models import VacancyUser, VacancyUserCall
    from vacancy.services.observers.call_observer import VacancyAfterStartCallFailObserver

    employer = EmployerFactory()
    worker_start_only = WorkerFactory()  # rejected START → must NOT be blocked by this observer
    worker_after_start = WorkerFactory()  # rejected AFTER_START → must be blocked

    group = GroupFactory(status="process")
    channel = ChannelFactory()
    vacancy = _create_active_vacancy(employer, group, channel)

    # Worker 1: rejected in START roll-call only
    vu1 = VacancyUser.objects.create(user=worker_start_only, vacancy=vacancy, status=Status.MEMBER)
    VacancyUserCall.objects.create(vacancy_user=vu1, call_type=CallType.START, status=CallStatus.REJECT)

    # Worker 2: rejected in AFTER_START roll-call
    vu2 = VacancyUser.objects.create(user=worker_after_start, vacancy=vacancy, status=Status.MEMBER)
    VacancyUserCall.objects.create(vacancy_user=vu2, call_type=CallType.AFTER_START, status=CallStatus.REJECT)

    notifier = MagicMock()
    with patch("vacancy.services.observers.call_observer.GroupService.kick_user"):
        VacancyAfterStartCallFailObserver(notifier=notifier).update("event", {"vacancy": vacancy})

    assert not UserBlock.objects.filter(user=worker_start_only, is_active=True).exists(), (
        "START-only reject must NOT be blocked by VacancyAfterStartCallFailObserver"
    )
    assert UserBlock.objects.filter(user=worker_after_start, is_active=True).exists(), (
        "AFTER_START reject must be blocked by VacancyAfterStartCallFailObserver"
    )


# ---------------------------------------------------------------------------
# 11. vacancy_reinvite_worker unblocks user and sends bot message
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_reinvite_worker_unblocks_and_sends_message(client):
    """vacancy_reinvite_worker must remove active block and send invite via bot."""
    from telegram.handlers.bot_instance import bot
    from user.choices import BlockType
    from user.models import UserBlock
    from user.services import BlockService

    admin = UserFactory(is_staff=True)
    worker = WorkerFactory()
    BlockService.block_user(worker, block_type=BlockType.TEMPORARY)
    assert UserBlock.objects.filter(user=worker, is_active=True).exists()

    group = GroupFactory(status="process", invite_link="https://t.me/+testgroup")
    channel = ChannelFactory()
    vacancy = _create_active_vacancy(admin, group, channel)

    client.force_login(admin)
    url = reverse("vacancy:reinvite_worker", kwargs={"pk": vacancy.pk, "user_id": worker.pk})

    with patch.object(bot, "send_message") as mock_send:
        response = client.post(url)

    assert response.status_code == 302
    assert not UserBlock.objects.filter(user=worker, is_active=True).exists(), "Block must be removed after reinvite"
    mock_send.assert_called()
    # View calls: bot.send_message(target_user.id, "...", reply_markup=markup)
    first_positional_arg = mock_send.call_args[0][0] if mock_send.call_args[0] else None
    assert first_positional_arg == worker.id, (
        f"send_message must target worker.id={worker.id}, got {first_positional_arg}"
    )
