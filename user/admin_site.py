from django.contrib import admin
from django.contrib.auth.models import Group as AuthGroup

# Скрываем стандартные Django auth Groups из админки
admin.site.unregister(AuthGroup)

# Скрываем simplejwt token blacklist
try:
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken, OutstandingToken
    )
    admin.site.unregister(BlacklistedToken)
    admin.site.unregister(OutstandingToken)
except Exception:
    pass
