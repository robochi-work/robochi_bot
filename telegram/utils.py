import hashlib
import hmac
import json
import logging
import time
from typing import Optional, Any
from urllib.parse import parse_qsl
from django.conf import settings

from user.models import User


logger = logging.getLogger(__name__)

def check_webapp_signature(init_data: str) -> tuple[bool, Optional[int]]:
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
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed_data.items())
    )

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

    return True, user_id


def get_or_create_user(user_id: int, **kwargs: dict[str, Any]) -> tuple[User, bool]:
    created = False
    try:
        logger.debug(f'get user {user_id}')
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        try:
            logger.debug(f'user {user_id} does not exist')
            user = User(
                id=user_id,
                username=kwargs.get('username'),
                language_code=kwargs.get('language_code', 'uk'),
            )
            user.save()
            created = True
            logger.info(f'Create new user {user}')
        except Exception as ex:
            logger.error(f'failed to create new user {user_id} {ex=}')
            user = User(
                id=user_id,
            )
            user.save()

    return user, created