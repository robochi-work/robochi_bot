import hashlib
import hmac
import json
import logging
from operator import itemgetter
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
        parsed_data = dict(parse_qsl(init_data))
    except ValueError:
        return False, user_id

    if "hash" not in parsed_data:
        return False, user_id

    hash_ = parsed_data.pop('hash')
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed_data.items(), key=itemgetter(0))
    )
    secret_key = hmac.new(
        key=b"WebAppData", msg=settings.TELEGRAM_BOT_TOKEN.encode(), digestmod=hashlib.sha256
    )
    calculated_hash = hmac.new(
        key=secret_key.digest(), msg=data_check_string.encode(), digestmod=hashlib.sha256
    ).hexdigest()

    result = calculated_hash == hash_

    if result:
        user_id = json.loads(parsed_data['user'])['id']

    return result, user_id


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
                **kwargs,
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