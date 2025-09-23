from django.conf import settings
from django.urls import path
from . import views


app_name = 'telegram'
urlpatterns = [
    path(f'webhook-{settings.TELEGRAM_BOT_TOKEN[-10:]}/', views.telegram_webhook, name='telegram_webhook'),
    path(f'check-web-app/', views.check, name='telegram_check_web_app'),
    path(f'authenticate-web-app/', views.authenticate_web_app, name='telegram_authenticate_web_app'),
]
