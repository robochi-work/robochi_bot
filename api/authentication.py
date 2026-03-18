import hmac
import hashlib
import json
import time
from urllib.parse import parse_qs, unquote

from django.conf import settings


def validate_telegram_init_data(init_data_raw: str, max_age_seconds: int = 86400) -> dict | None:
    """
    Validates Telegram WebApp initData using HMAC-SHA256.
    Returns parsed user data dict or None if invalid.
    """
    parsed = parse_qs(init_data_raw, keep_blank_values=True)
    hash_value = parsed.pop('hash', [None])[0]
    if not hash_value:
        return None
    # Remove signature field if present (newer Telegram versions)
    parsed.pop('signature', None)

    # Build data_check_string: sort params alphabetically, join with \n
    data_check_string = '\n'.join(
        f'{k}={v[0]}' for k, v in sorted(parsed.items())
    )

    # Two-layer HMAC: first derive secret key, then compute hash
    secret_key = hmac.new(
        b'WebAppData',
        settings.TELEGRAM_BOT_TOKEN.encode(),
        hashlib.sha256
    ).digest()

    computed_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, hash_value):
        return None

    # Check auth_date freshness
    auth_date = int(parsed.get('auth_date', [0])[0])
    if time.time() - auth_date > max_age_seconds:
        return None

    # Parse user JSON
    user_raw = parsed.get('user', ['{}'])[0]
    user_data = json.loads(unquote(user_raw))
    return {
        'user': user_data,
        'auth_date': auth_date,
        'hash': hash_value,
    }
