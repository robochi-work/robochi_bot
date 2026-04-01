import hashlib
import hmac
import json
import logging
import time
from typing import Any
from urllib.parse import parse_qsl

from django.conf import settings

from user.models import User

logger = logging.getLogger(__name__)


def check_webapp_signature(init_data: str) -> tuple[bool, int | None]:
    """
    Check incoming WebApp init data signature
    Source: https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app
    """
    user_id = None

    try:
        parsed_data = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return False, user_id

    if "hash" not in parsed_data:
        return False, user_id

    hash_ = parsed_data.pop("hash")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))

    secret_key = hmac.new(
        key=b"WebAppData",
        msg=settings.TELEGRAM_BOT_TOKEN.encode("utf-8"),
        digestmod=hashlib.sha256,
    )
    calculated_hash = hmac.new(
        key=secret_key.digest(),
        msg=data_check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if calculated_hash != hash_:
        logger.warning("webapp_auth_failed", extra={"reason": "invalid_signature"})
        return False, user_id

    # Проверка auth_date — защита от replay-атак
    auth_date = parsed_data.get("auth_date")
    if not auth_date:
        return False, user_id
    if time.time() - int(auth_date) > 86400:
        logger.warning("WEBAPP AUTH initData expired, auth_date=%s", auth_date)
        return False, user_id

    if "user" in parsed_data:
        user_id = json.loads(parsed_data["user"])["id"]

    logger.info("webapp_auth_success", extra={"user_id": user_id})
    return True, user_id


def _build_full_name(first_name: str = "", last_name: str = "") -> str:
    """Combine first_name and last_name from Telegram into a single full_name string."""
    parts = [p for p in (first_name or "", last_name or "") if p.strip()]
    return " ".join(parts) or None


def notify_admins_new_user(user: User) -> None:
    """Send notification to all admins about a new user registration."""
    from django.conf import settings

    from telegram.handlers.bot_instance import get_bot

    admin_ids = getattr(settings, "ADMIN_TELEGRAM_IDS", [])
    if not admin_ids:
        logger.warning("ADMIN_TELEGRAM_IDS not configured, skipping new user notification")
        return

    text = (
        "🆕 <b>Новий користувач</b>\n\n"
        f"<b>ID:</b> <code>{user.pk}</code>\n"
        f"<b>Ім'я:</b> {user.full_name or '—'}\n"
        f"<b>Username:</b> @{user.username}\n"
        if user.username
        else "🆕 <b>Новий користувач</b>\n\n"
        f"<b>ID:</b> <code>{user.pk}</code>\n"
        f"<b>Ім'я:</b> {user.full_name or '—'}\n"
        f"<b>Username:</b> —\n"
    )
    if user.phone_number:
        text += f"<b>Телефон:</b> {user.phone_number}\n"

    bot = get_bot()
    for admin_id in admin_ids:
        try:
            bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML")
            logger.info(f"New user notification sent to admin {admin_id}")
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")


def get_or_create_user(user_id: int, **kwargs: dict[str, Any]) -> tuple[User, bool]:
    created = False
    full_name = _build_full_name(
        kwargs.get("first_name", ""),
        kwargs.get("last_name", ""),
    )

    try:
        logger.debug(f"get user {user_id}")
        user = User.objects.get(id=user_id)

        # Update user data from Telegram profile on every /start
        # so that changes in username or name are always reflected
        update_fields = []
        new_username = kwargs.get("username")
        if new_username and user.username != new_username:
            user.username = new_username
            update_fields.append("username")
        if full_name and user.full_name != full_name:
            user.full_name = full_name
            update_fields.append("full_name")
        if not user.telegram_id:
            user.telegram_id = user_id
            update_fields.append("telegram_id")
        if update_fields:
            user.save(update_fields=update_fields)
            logger.info(f"Updated user {user_id} fields: {update_fields}")

    except User.DoesNotExist:
        try:
            logger.debug(f"user {user_id} does not exist")
            user = User(
                id=user_id,
                telegram_id=user_id,
                username=kwargs.get("username"),
                full_name=full_name,
            )
            user.save()
            created = True
            logger.info(f"Create new user {user}")
            # notification moved to contact handler (after phone is saved)
        except Exception as ex:
            logger.error(f"failed to create new user {user_id} {ex=}")
            user = User(id=user_id)
            user.save()

    return user, created
