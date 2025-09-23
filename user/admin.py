from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm
from django.utils.html import format_html
from django.urls import reverse

from .forms import UserChangeForm, UserCreationForm
from .models import User, UserFeedback, UserWorkProfileInUser


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display = ('id', 'telegram_link', 'full_name', 'phone_number', 'is_staff')
    search_fields = ('username', 'full_name')
    ordering = ('id',)

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('gender', 'full_name', 'phone_number', 'birth_year', 'language_code')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser',)}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )


    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2'),
        }),
    )

    @admin.display(description="Telegram")
    def telegram_link(self, obj):
        if obj.username:
            return format_html('<a href="https://t.me/{}" target="_blank">@{}</a>', obj.username, obj.username)
        return "-"


@admin.register(UserFeedback)
class UserFeedbackAdmin(admin.ModelAdmin):
    list_display = ('owner', 'user', )


@admin.register(UserWorkProfileInUser)
class UserWorkProfileInUserAdmin(admin.ModelAdmin):
    list_display = ('user', 'city', 'role', 'is_completed')