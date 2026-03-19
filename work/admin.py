from django.contrib import admin
from work.models import AgreementText, UserWorkProfile


@admin.register(AgreementText)
class AgreementTextAdmin(admin.ModelAdmin):
    list_display = ("role", "title", "updated_at")
    list_editable = ("title",)


@admin.register(UserWorkProfile)
class UserWorkProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "city", "is_completed", "created_at")
    list_filter = ("role", "city", "is_completed")
    search_fields = ("user__username", "user__full_name")
