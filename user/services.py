from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db import models, transaction

from user.choices import BlockReason, BlockType
from user.models import AuthIdentity, UserBlock

logger = logging.getLogger(__name__)

User = get_user_model()


def get_or_create_user_from_telegram(
    *, telegram_id: int, full_name: str = "", username: str = "", phone_number: str = ""
) -> tuple:
    """
    Находит или создаёт пользователя по Telegram ID.
    Обновляет full_name и username при каждом входе.
    Возвращает (user, created).
    """
    with transaction.atomic():
        user, created = User.objects.get_or_create(
            id=telegram_id,
            defaults={
                "telegram_id": telegram_id,
                "full_name": full_name,
                "username": username or f"tg_{telegram_id}",
                "phone_number": phone_number,
            },
        )
        if not created:
            update_fields = []
            if full_name and user.full_name != full_name:
                user.full_name = full_name
                update_fields.append("full_name")
            if username and user.username != username:
                user.username = username
                update_fields.append("username")
            if update_fields:
                user.save(update_fields=update_fields)

        # Ensure AuthIdentity exists
        AuthIdentity.objects.get_or_create(
            provider=AuthIdentity.Provider.TELEGRAM,
            provider_uid=str(telegram_id),
            defaults={"user": user},
        )
        if phone_number:
            AuthIdentity.objects.get_or_create(
                provider=AuthIdentity.Provider.PHONE,
                provider_uid=phone_number,
                defaults={"user": user},
            )

    return user, created


class BlockService:
    @staticmethod
    def is_blocked(user) -> bool:
        from user.models import UserBlock

        return (
            UserBlock.objects.filter(
                user=user,
                is_active=True,
            )
            .filter(models.Q(block_type=BlockType.PERMANENT) | models.Q(block_type=BlockType.TEMPORARY))
            .exists()
        )

    @staticmethod
    def is_permanently_blocked(user) -> bool:
        from user.models import UserBlock

        return UserBlock.objects.filter(user=user, is_active=True, block_type=BlockType.PERMANENT).exists()

    @staticmethod
    def is_temporarily_blocked(user) -> bool:
        from user.models import UserBlock

        return UserBlock.objects.filter(
            user=user,
            is_active=True,
            block_type=BlockType.TEMPORARY,
        ).exists()

    @staticmethod
    def get_active_block(user) -> UserBlock | None:
        return (
            UserBlock.objects.filter(
                user=user,
                is_active=True,
            )
            .order_by("-created_at")
            .first()
        )

    @staticmethod
    def block_user(
        user,
        block_type: str,
        reason: str = BlockReason.MANUAL,
        blocked_by=None,
        blocked_until=None,
        comment: str = "",
    ) -> UserBlock:
        block = UserBlock.objects.create(
            user=user,
            block_type=block_type,
            reason=reason,
            blocked_by=blocked_by,
            blocked_until=blocked_until,
            comment=comment,
        )
        logger.info("block_created", extra={"user_id": user.id, "block_type": block_type, "reason": reason})
        if block_type == BlockType.PERMANENT:
            user.is_active = False
            user.save(update_fields=["is_active"])
        return block

    @staticmethod
    def unblock_user(block_id: int) -> None:
        from user.models import UserBlock

        block = UserBlock.objects.select_related("user").get(pk=block_id)
        block.is_active = False
        block.save(update_fields=["is_active"])
        logger.info("block_removed", extra={"user_id": block.user.id})
        if block.block_type == BlockType.PERMANENT:
            user = block.user
            user.is_active = True
            user.save(update_fields=["is_active"])

    @staticmethod
    def auto_block_rollcall_reject(user, blocked_by=None) -> UserBlock:
        return BlockService.block_user(
            user=user,
            block_type=BlockType.TEMPORARY,
            reason=BlockReason.ROLLCALL_REJECT,
            blocked_by=blocked_by,
        )

    @staticmethod
    def auto_block_employer_unpaid(user) -> UserBlock:
        return BlockService.block_user(
            user=user,
            block_type=BlockType.TEMPORARY,
            reason=BlockReason.UNPAID,
            blocked_until=None,
        )


def find_user_by_phone(*, phone_number: str):
    """Поиск пользователя по номеру телефона через AuthIdentity."""
    try:
        identity = AuthIdentity.objects.select_related("user").get(
            provider=AuthIdentity.Provider.PHONE,
            provider_uid=phone_number,
        )
        return identity.user
    except AuthIdentity.DoesNotExist:
        return None
