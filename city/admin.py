from django.contrib import admin
from parler.admin import TranslatableAdmin

from .models import City


@admin.register(City)
class CityAdmin(TranslatableAdmin):
    list_display = ('name', )

