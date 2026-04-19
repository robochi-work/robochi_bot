from django.conf import settings
from django.urls import path

from . import views

app_name = "telegram"

urlpatterns = [
    path(f"webhook-{settings.TELEGRAM_WEBHOOK_SECRET}/", views.telegram_webhook, name="telegram_webhook"),
    path("check-web-app/", views.check, name="telegram_check_web_app"),
    path("authenticate-web-app/", views.authenticate_web_app, name="telegram_authenticate_web_app"),
]
