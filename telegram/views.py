from django.http import HttpResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.core.handlers.wsgi import WSGIRequest
from django.contrib.auth import login
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from urllib.parse import unquote
import telebot

from telegram.handlers import bot
from .utils import check_webapp_signature, get_or_create_user


def check(request: WSGIRequest) -> HttpResponse:
    return render(request, 'telegram/check.html')

def authenticate_web_app(request: WSGIRequest):
    init_data = request.GET.get('init_data', '')
    next_path = unquote(request.GET.get('next', '/'))

    # secure open-redirect
    if not url_has_allowed_host_and_scheme(
       url=next_path,
       allowed_hosts={request.get_host()},
       require_https=request.is_secure()
    ):
        next_path = '/'

    is_valid, user_id = check_webapp_signature(init_data)
    if is_valid and user_id:
        user, _ = get_or_create_user(user_id=user_id)
        login(request, user)
        return redirect(next_path)

    admin_login_url = reverse('admin:login')
    return redirect(f"{admin_login_url}?next={next_path}")

@csrf_exempt
def telegram_webhook(request: WSGIRequest) -> HttpResponse:
    if request.method == 'POST':
        json_str = request.body.decode('UTF-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return HttpResponse('ok')
    return HttpResponse('Only POST allowed', status=405)