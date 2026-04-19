from django.contrib import admin
from django.contrib.auth.models import Group as AuthGroup

# Скрываем стандартные Django auth Groups из админки
admin.site.unregister(AuthGroup)

# Скрываем simplejwt token blacklist
try:
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    admin.site.unregister(BlacklistedToken)
    admin.site.unregister(OutstandingToken)
except Exception:
    pass

# Кастомный порядок секций и заголовки
admin.site.site_header = "Robochi Bot"
admin.site.site_title = "Robochi Admin"
admin.site.index_title = "Панель керування"

APP_ORDER = [
    "user",  # Користувачі
    "vacancy",  # Вакансії та робота
    "city",  # Міста та канали
    "telegram",  # Телеграм групи
    "payment",  # Оплата
    "work",  # Документи
]

_original_get_app_list = admin.AdminSite.get_app_list


def custom_get_app_list(self, request, app_label=None):
    app_list = _original_get_app_list(self, request, app_label=app_label)
    order_map = {app: i for i, app in enumerate(APP_ORDER)}
    app_list.sort(key=lambda x: order_map.get(x["app_label"], 999))
    return app_list


admin.AdminSite.get_app_list = custom_get_app_list
