from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .forms import UserChangeForm, UserCreationForm
from .models import User, AuthIdentity, UserFeedback
from work.models import UserWorkProfile
from work.choices import WorkProfileRole


class AuthIdentityInline(admin.TabularInline):
    model = AuthIdentity
    extra = 0
    readonly_fields = ('created_at',)


class UserWorkProfileInline(admin.StackedInline):
    model = UserWorkProfile
    can_delete = False
    extra = 0
    max_num = 1
    fields = (
        'role', 'city', 'phone_number', 'agreement_accepted', 'is_completed',
        'multi_city_enabled', 'allowed_cities',
        'created_at',
    )
    readonly_fields = ('created_at',)
    filter_horizontal = ('allowed_cities',)
    verbose_name = _('Work profile')
    verbose_name_plural = _('Work profile')


class UserFeedbackReceivedInline(admin.TabularInline):
    model = UserFeedback
    fk_name = 'user'
    extra = 0
    readonly_fields = ('owner', 'text', 'created_at')
    verbose_name = _('Received feedback')
    verbose_name_plural = _('Received feedbacks')

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class RoleFilter(admin.SimpleListFilter):
    title = _('Role')
    parameter_name = 'role'

    def lookups(self, request, model_admin):
        return WorkProfileRole.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(work_profile__role=self.value())
        return queryset


class CityFilter(admin.SimpleListFilter):
    title = _('City')
    parameter_name = 'city'

    def lookups(self, request, model_admin):
        from city.models import City
        return [(c.pk, c.safe_translation_getter('name', any_language=True)) for c in City.objects.all()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(work_profile__city_id=self.value())
        return queryset


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    inlines = [UserWorkProfileInline, AuthIdentityInline, UserFeedbackReceivedInline]

    list_display = (
        'id', 'telegram_link', 'full_name', 'phone_number',
        'display_role', 'display_city', 'display_gender', 'is_staff', 'is_active',
    )
    list_filter = (RoleFilter, CityFilter, 'gender', 'is_staff', 'is_active')
    search_fields = ('username', 'full_name', 'phone_number')
    ordering = ('id',)

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal info'), {'fields': ('gender', 'full_name', 'phone_number', 'language_code')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2'),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('work_profile', 'work_profile__city')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        # Sync is_staff with administrator role
        if obj.is_staff:
            profile, _ = UserWorkProfile.objects.get_or_create(user=obj)
            if profile.role != WorkProfileRole.ADMINISTRATOR:
                profile.role = WorkProfileRole.ADMINISTRATOR
                profile.is_completed = True
                profile.save(update_fields=['role', 'is_completed'])
        else:
            profile = UserWorkProfile.objects.filter(user=obj).first()
            if profile and profile.role == WorkProfileRole.ADMINISTRATOR:
                profile.role = None
                profile.is_completed = False
                profile.save(update_fields=['role', 'is_completed'])

    @admin.display(description=_('Telegram'))
    def telegram_link(self, obj):
        if obj.username:
            return format_html(
                '<a href="https://t.me/{}" target="_blank">@{}</a>',
                obj.username, obj.username
            )
        return "-"

    @admin.display(description=_('Role'))
    def display_role(self, obj):
        profile = getattr(obj, 'work_profile', None)
        if profile and profile.role:
            return profile.get_role_display()
        return "-"

    @admin.display(description=_('City'))
    def display_city(self, obj):
        profile = getattr(obj, 'work_profile', None)
        if profile and profile.city:
            return profile.city.safe_translation_getter('name', any_language=True)
        return "-"

    @admin.display(description=_('Gender'))
    def display_gender(self, obj):
        profile = getattr(obj, 'work_profile', None)
        if profile and profile.role == WorkProfileRole.WORKER:
            if obj.gender:
                return obj.get_gender_display()
            return _('Not set')
        return "-"
