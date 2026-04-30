from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm
from django.db.models import Q
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from work.choices import WorkProfileRole
from work.models import UserWorkProfile

from .choices import BlockType
from .forms import UserChangeForm, UserCreationForm
from .models import AuthIdentity, User, UserBlock, UserFeedback


class UserBlockInline(admin.TabularInline):
    model = UserBlock
    fk_name = "user"
    extra = 0
    fields = ("block_type", "reason", "blocked_by", "blocked_until", "comment", "is_active", "created_at")
    readonly_fields = ("created_at",)
    verbose_name = "Блокування"
    verbose_name_plural = "Блокування"


class AuthIdentityInline(admin.TabularInline):
    model = AuthIdentity
    extra = 0
    readonly_fields = ("created_at",)


class UserWorkProfileInline(admin.StackedInline):
    model = UserWorkProfile
    can_delete = False
    extra = 0
    max_num = 1
    fields = (
        "role",
        "city",
        "agreement_accepted",
        "is_completed",
        "multi_city_enabled",
        "allowed_cities",
        "created_at",
    )
    readonly_fields = ("created_at",)
    filter_horizontal = ("allowed_cities",)
    verbose_name = _("Work profile")
    verbose_name_plural = _("Work profile")


class UserFeedbackReceivedInline(admin.TabularInline):
    model = UserFeedback
    fk_name = "user"
    extra = 0
    readonly_fields = ("owner", "text", "created_at")
    verbose_name = _("Received feedback")
    verbose_name_plural = _("Received feedbacks")

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class BlockedFilter(admin.SimpleListFilter):
    title = _("Block status")
    parameter_name = "blocked"

    def lookups(self, request, model_admin):
        return [
            ("active", "Активне блокування"),
            ("permanent", "Постійне"),
            ("temporary", "Тимчасове"),
            ("none", "Без блокування"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "active":
            return queryset.filter(
                Q(blocks__is_active=True, blocks__block_type=BlockType.PERMANENT)
                | Q(blocks__is_active=True, blocks__block_type=BlockType.TEMPORARY)
            ).distinct()
        if self.value() == "permanent":
            return queryset.filter(blocks__is_active=True, blocks__block_type=BlockType.PERMANENT).distinct()
        if self.value() == "temporary":
            return queryset.filter(
                blocks__is_active=True,
                blocks__block_type=BlockType.TEMPORARY,
            ).distinct()
        if self.value() == "none":
            return queryset.exclude(
                Q(blocks__is_active=True, blocks__block_type=BlockType.PERMANENT)
                | Q(blocks__is_active=True, blocks__block_type=BlockType.TEMPORARY)
            ).distinct()
        return queryset


class RoleFilter(admin.SimpleListFilter):
    title = _("Role")
    parameter_name = "role"

    def lookups(self, request, model_admin):
        return WorkProfileRole.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(work_profile__role=self.value())
        return queryset


class CityFilter(admin.SimpleListFilter):
    title = _("City")
    parameter_name = "city"

    def lookups(self, request, model_admin):
        from city.models import City

        return [(c.pk, c.safe_translation_getter("name", any_language=True)) for c in City.objects.all()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(work_profile__city_id=self.value())
        return queryset


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    inlines = [UserWorkProfileInline, AuthIdentityInline, UserFeedbackReceivedInline, UserBlockInline]

    list_display = (
        "id",
        "telegram_link",
        "full_name",
        "phone_number",
        "display_role",
        "display_city",
        "display_gender",
        "is_staff",
        "is_active",
        "display_block_status",
    )
    list_filter = (RoleFilter, CityFilter, BlockedFilter, "gender", "is_staff", "is_active")
    search_fields = ("username", "full_name", "phone_number", "contact_phone")
    ordering = ("id",)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("gender", "full_name", "phone_number", "contact_phone", "language_code")}),
        (_("Permissions"), {"fields": ("is_active", "is_staff", "is_superuser")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2"),
            },
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("work_profile", "work_profile__city")
        if not request.user.is_superuser:
            qs = qs.filter(is_staff=False)
        return qs

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            readonly.extend(["is_staff", "is_superuser", "is_active"])
        return readonly

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_staff and not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        # Sync is_staff with administrator role
        if obj.is_staff:
            profile, _ = UserWorkProfile.objects.get_or_create(user=obj)
            if profile.role != WorkProfileRole.ADMINISTRATOR:
                profile.role = WorkProfileRole.ADMINISTRATOR
                profile.is_completed = True
                profile.save(update_fields=["role", "is_completed"])
        else:
            profile = UserWorkProfile.objects.filter(user=obj).first()
            if profile and profile.role == WorkProfileRole.ADMINISTRATOR:
                profile.role = None
                profile.is_completed = False
                profile.save(update_fields=["role", "is_completed"])

    @admin.display(description=_("Telegram"))
    def telegram_link(self, obj):
        if obj.username:
            return format_html('<a href="https://t.me/{}" target="_blank">@{}</a>', obj.username, obj.username)
        return "-"

    @admin.display(description=_("Role"))
    def display_role(self, obj):
        profile = getattr(obj, "work_profile", None)
        if profile and profile.role:
            return profile.get_role_display()
        return "-"

    @admin.display(description=_("City"))
    def display_city(self, obj):
        profile = getattr(obj, "work_profile", None)
        if profile and profile.city:
            return profile.city.safe_translation_getter("name", any_language=True)
        return "-"

    @admin.display(description=_("Block"))
    def display_block_status(self, obj):
        active = obj.blocks.filter(is_active=True).order_by("-created_at").first()
        if not active:
            return "✅"
        if active.block_type == BlockType.PERMANENT:
            return format_html('<span style="color:#c0392b">🔴 Постійне</span>')
        return format_html('<span style="color:#e67e22">🟡 Тимчасове</span>')

    @admin.display(description=_("Gender"))
    def display_gender(self, obj):
        profile = getattr(obj, "work_profile", None)
        if profile and profile.role == WorkProfileRole.WORKER:
            if obj.gender:
                return obj.get_gender_display()
            return _("Not set")
        return "-"


@admin.register(UserFeedback)
class UserFeedbackAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "owner", "rating", "is_auto", "short_text", "created_at")
    list_filter = ("rating", "is_auto", "created_at")
    search_fields = ("user__username", "user__full_name", "owner__username", "owner__full_name", "text")
    list_editable = ("rating",)
    readonly_fields = ("owner", "user", "is_auto", "extra", "created_at")

    @admin.display(description="Текст")
    def short_text(self, obj):
        return obj.text[:50] if obj.text else "-"
