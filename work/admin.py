from django.contrib import admin

from work.models import AgreementText


@admin.register(AgreementText)
class AgreementTextAdmin(admin.ModelAdmin):
    list_display = ("role", "title", "updated_at")
    list_editable = ("title",)
