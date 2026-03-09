import json
import logging
from urllib.parse import unquote, parse_qsl

from django.contrib.auth import login
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.core.handlers.wsgi import WSGIRequest
from django.views.decorators.csrf import csrf_exempt

import telebot

from telegram.handlers.bot_instance import get_bot
from .utils import check_webapp_signature, get_or_create_user

logger = logging.getLogger(__name__)


def check(request: WSGIRequest) -> HttpResponse:
    return render(request, "telegram/check.html")


def authenticate_web_app(request: WSGIRequest):
    init_data = request.GET.get("init_data", "")
    next_path = unquote(request.GET.get("next", "/"))

    logger.warning(
        "WEBAPP AUTH HIT path=%s host=%s secure=%s",
        request.path,
        request.get_host(),
        request.is_secure(),
    )
    logger.warning(
        "WEBAPP AUTH query next(raw)=%r next(decoded)=%r init_data_len=%s",
        request.GET.get("next"),
        next_path,
        len(init_data or ""),
    )

    logger.warning("WEBAPP AUTH allowed_hosts=%s", {request.get_host()})

    if not url_has_allowed_host_and_scheme(
        url=next_path,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_path = "/"

    is_valid, user_id = check_webapp_signature(init_data)
    logger.warning("WEBAPP AUTH signature is_valid=%s user_id=%s", is_valid, user_id)

    if is_valid and user_id:
        # user_id = Telegram user id. � ����� ������� �� �������� � User.telegram_id.
        if request.user.is_authenticated:
            current_tid = getattr(request.user, "telegram_id", None)
            if current_tid and current_tid != user_id:
                from django.contrib.auth import logout
                logout(request)

        parsed_data = dict(parse_qsl(init_data))
        user_data = json.loads(parsed_data.get('user', '{}'))
        user, _ = get_or_create_user(
            user_id=user_id,
            username=user_data.get('username'),
            language_code=user_data.get('language_code', 'uk'),
        )

        logger.warning("WEBAPP AUTH logging-in telegram_user_id=%s user_pk=%s", user_id, user.pk)
        login(request, user)
        return redirect(next_path)

    admin_login_url = reverse("admin:login")
    return redirect(f"{admin_login_url}?next={next_path}")


@csrf_exempt
def telegram_webhook(request: WSGIRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponse("Only POST allowed", status=405)

    try:
        json_str = request.body.decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        get_bot().process_new_updates([update])
    except Exception:
        logger.exception("Webhook processing failed. body=%r", (request.body[:200] if request.body else b""))

    return HttpResponse("ok")
