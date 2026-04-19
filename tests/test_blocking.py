"""
Tests for BlockService (user/services.py).

Covers:
- block_user (TEMPORARY / PERMANENT)
- is_blocked / is_temporarily_blocked / is_permanently_blocked
- get_active_block
- unblock_user — restores is_active for permanent blocks
- auto_block helpers
"""

import pytest

from user.choices import BlockReason, BlockType
from user.services import BlockService


@pytest.mark.django_db
def test_new_user_is_not_blocked(user_factory):
    user = user_factory()
    assert BlockService.is_blocked(user) is False
    assert BlockService.get_active_block(user) is None


@pytest.mark.django_db
def test_temporary_block(user_factory):
    user = user_factory()

    block = BlockService.block_user(user, block_type=BlockType.TEMPORARY)

    assert BlockService.is_blocked(user) is True
    assert BlockService.is_temporarily_blocked(user) is True
    assert BlockService.is_permanently_blocked(user) is False
    # Temporary block must NOT deactivate the user account
    user.refresh_from_db()
    assert user.is_active is True
    assert block.block_type == BlockType.TEMPORARY


@pytest.mark.django_db
def test_permanent_block_deactivates_user(user_factory):
    user = user_factory()

    block = BlockService.block_user(user, block_type=BlockType.PERMANENT)

    assert BlockService.is_permanently_blocked(user) is True
    assert BlockService.is_blocked(user) is True
    user.refresh_from_db()
    assert user.is_active is False
    assert block.block_type == BlockType.PERMANENT


@pytest.mark.django_db
def test_unblock_temporary(user_factory):
    user = user_factory()
    block = BlockService.block_user(user, block_type=BlockType.TEMPORARY)

    BlockService.unblock_user(block.id)

    assert BlockService.is_blocked(user) is False
    # Temporary unblock must not change is_active
    user.refresh_from_db()
    assert user.is_active is True


@pytest.mark.django_db
def test_unblock_permanent_reactivates_user(user_factory):
    user = user_factory()
    block = BlockService.block_user(user, block_type=BlockType.PERMANENT)
    user.refresh_from_db()
    assert user.is_active is False

    BlockService.unblock_user(block.id)

    assert BlockService.is_blocked(user) is False
    user.refresh_from_db()
    assert user.is_active is True


@pytest.mark.django_db
def test_get_active_block_returns_latest(user_factory):
    user = user_factory()
    BlockService.block_user(user, block_type=BlockType.TEMPORARY, reason=BlockReason.MANUAL)
    block2 = BlockService.block_user(user, block_type=BlockType.TEMPORARY, reason=BlockReason.OTHER)

    active = BlockService.get_active_block(user)
    assert active is not None
    assert active.id == block2.id


@pytest.mark.django_db
def test_block_with_reason_and_comment(user_factory):
    user = user_factory()

    block = BlockService.block_user(
        user,
        block_type=BlockType.TEMPORARY,
        reason=BlockReason.ROLLCALL_REJECT,
        comment="Не з'явився на перекличку",
    )

    assert block.reason == BlockReason.ROLLCALL_REJECT
    assert block.comment == "Не з'явився на перекличку"
    assert block.is_active is True


@pytest.mark.django_db
def test_auto_block_rollcall_reject(user_factory):
    user = user_factory()

    block = BlockService.auto_block_rollcall_reject(user)

    assert block.reason == BlockReason.ROLLCALL_REJECT
    assert block.block_type == BlockType.TEMPORARY
    assert BlockService.is_blocked(user) is True


@pytest.mark.django_db
def test_auto_block_employer_unpaid(user_factory):
    user = user_factory()

    block = BlockService.auto_block_employer_unpaid(user)

    assert block.reason == BlockReason.UNPAID
    assert block.block_type == BlockType.TEMPORARY
    assert BlockService.is_blocked(user) is True


@pytest.mark.django_db
def test_block_with_blocked_by(user_factory):
    admin = user_factory(is_staff=True)
    target = user_factory()

    block = BlockService.block_user(
        target,
        block_type=BlockType.PERMANENT,
        blocked_by=admin,
    )

    assert block.blocked_by_id == admin.id
