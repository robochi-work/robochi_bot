"""
Tests for check_webapp_signature (telegram/utils.py).

The function validates the HMAC-SHA256 signature that Telegram attaches
to WebApp init_data.  We build a correctly signed payload in-process so
the tests are self-contained and don't require a live bot.
"""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from django.conf import settings

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _build_init_data(user_id: int, extra_age: int = 0) -> str:
    """
    Build a properly signed init_data string using the current
    TELEGRAM_BOT_TOKEN from Django settings.

    :param user_id:    Telegram user ID to embed in the payload.
    :param extra_age:  Seconds to subtract from now (simulate old tokens).
    """
    bot_token: str = settings.TELEGRAM_BOT_TOKEN
    auth_date = int(time.time()) - extra_age
    user_json = json.dumps({"id": user_id, "first_name": "Test"})

    params = {
        "auth_date": str(auth_date),
        "user": user_json,
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))

    # Mirror the two-stage HMAC from telegram/utils.py exactly
    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode(),
        digestmod=hashlib.sha256,
    )
    signature = hmac.new(
        key=secret_key.digest(),
        msg=data_check_string.encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()

    params["hash"] = signature
    return urlencode(params)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_valid_signature_returns_true_and_user_id():
    from telegram.utils import check_webapp_signature

    init_data = _build_init_data(user_id=123456789)
    valid, user_id = check_webapp_signature(init_data)

    assert valid is True
    assert user_id == 123456789


@pytest.mark.django_db
def test_invalid_hash_returns_false():
    from telegram.utils import check_webapp_signature

    init_data = _build_init_data(user_id=111)
    # Corrupt the hash value
    tampered = init_data.replace(init_data.split("hash=")[1][:10], "0000000000")
    valid, user_id = check_webapp_signature(tampered)

    assert valid is False
    assert user_id is None


@pytest.mark.django_db
def test_missing_hash_returns_false():
    from telegram.utils import check_webapp_signature

    # Build a payload without a hash field at all
    init_data = urlencode({"auth_date": str(int(time.time())), "user": '{"id":1}'})
    valid, user_id = check_webapp_signature(init_data)

    assert valid is False
    assert user_id is None


@pytest.mark.django_db
def test_expired_token_returns_false():
    from telegram.utils import check_webapp_signature

    # 25 hours old — beyond the 24 h replay-attack window
    init_data = _build_init_data(user_id=999, extra_age=90_000)
    valid, user_id = check_webapp_signature(init_data)

    assert valid is False


@pytest.mark.django_db
def test_empty_string_returns_false():
    from telegram.utils import check_webapp_signature

    valid, user_id = check_webapp_signature("")

    assert valid is False
    assert user_id is None


@pytest.mark.django_db
def test_signature_with_different_token_is_invalid(settings):
    from telegram.utils import check_webapp_signature

    # Build init_data with one token, then change the setting to another
    init_data = _build_init_data(user_id=42)
    settings.TELEGRAM_BOT_TOKEN = "9:AnotherToken"

    valid, _ = check_webapp_signature(init_data)
    assert valid is False
