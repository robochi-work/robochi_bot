from typing import Any

from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.utils.translation import gettext_lazy as _

from user.choices import USER_GENDER_CHOICES, BlockReason, BlockType


class CustomUserManager(UserManager):
    def create_user(self, **extra_fields: Any):
        user = self.model(**extra_fields)
        user.set_password(extra_fields.get("password"))
        user.save()
        return user

    def create_superuser(self, **extra_fields: Any):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(**extra_fields)


class User(AbstractUser):
    telegram_id = models.BigIntegerField(unique=True, db_index=True, null=True, blank=True)
    username = models.CharField(max_length=150, blank=True, null=True, unique=False, verbose_name=_("Username"))
    first_name = None
    last_name = None
    full_name = models.CharField(_("Full name"), max_length=150, blank=True, null=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True, verbose_name=_("Phone number"))
    contact_phone = models.CharField(max_length=20, blank=True, default="", verbose_name=_("Contact phone"))
    language_code = models.CharField(
        max_length=10,
        choices=settings.LANGUAGES,
        default=settings.LANGUAGE_CODE,
        verbose_name=_("Language"),
    )
    gender = models.CharField(choices=USER_GENDER_CHOICES, blank=True, null=True, verbose_name=_("Gender"))
    USERNAME_FIELD = "id"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    class Meta:
        db_table = "user"
        verbose_name = _("User")
        verbose_name_plural = _("Users")

    def __str__(self) -> str:
        return f"User: {self.pk} {self.username}"


class AuthIdentity(models.Model):
    class Provider(models.TextChoices):
        TELEGRAM = "telegram", "Telegram"
        PHONE = "phone", "Phone"
        EMAIL = "email", "Email"
        GOOGLE = "google", "Google"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="auth_identities")
    provider = models.CharField(max_length=50, choices=Provider.choices)
    provider_uid = models.CharField(max_length=255)
    extra_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("provider", "provider_uid")
        verbose_name = "Auth Identity"
        verbose_name_plural = "Auth Identities"

    def __str__(self):
        return f"{self.provider}:{self.provider_uid} → {self.user}"


class UserBlock(models.Model):
    user = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        related_name="blocks",
        verbose_name=_("User"),
    )
    block_type = models.CharField(
        max_length=20,
        choices=BlockType.choices,
        verbose_name=_("Block type"),
    )
    reason = models.CharField(
        max_length=30,
        choices=BlockReason.choices,
        default=BlockReason.MANUAL,
        verbose_name=_("Reason"),
    )
    blocked_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blocks_issued",
        verbose_name=_("Blocked by"),
    )
    blocked_until = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Blocked until"),
    )
    comment = models.TextField(blank=True, default="", verbose_name=_("Comment"))
    is_active = models.BooleanField(default=True, verbose_name=_("Is active"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    class Meta:
        verbose_name = _("Блокування користувача")
        verbose_name_plural = _("Блокування користувачів")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user} — {self.block_type} ({self.reason})"


class UserFeedback(models.Model):
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="feedbacks_given",
        verbose_name=_("Feedback author"),
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="feedbacks_received",
        verbose_name=_("Feedback recipient"),
    )
    RATING_CHOICES = [
        ("like", "Лайк"),
        ("dislike", "Дизлайк"),
        ("none", "Без оцінки"),
    ]

    text = models.TextField(blank=True, default="")
    rating = models.CharField(
        max_length=10,
        choices=RATING_CHOICES,
        default="none",
        verbose_name="Оцінка",
    )
    is_auto = models.BooleanField(default=False, verbose_name="Автоматичний")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    extra = models.JSONField(blank=True, default=dict)

    class Meta:
        verbose_name = _("User feedback")
        verbose_name_plural = _("User feedbacks")

    def __str__(self):
        return f"{self.owner} → {self.user} ({self.rating})"


class WorkerVoluntaryExit(models.Model):
    """Лог добровільних виходів рабочого з групи вакансії."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="voluntary_exits",
        verbose_name=_("User"),
    )
    vacancy = models.ForeignKey(
        "vacancy.Vacancy",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Vacancy"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    class Meta:
        verbose_name = _("Добровільний вихід")
        verbose_name_plural = _("Добровільні виходи")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} — {self.created_at}"


class AdminHelpRequest(models.Model):
    """Запит користувача на допомогу адміністратора."""

    STATUS_PENDING = "pending"
    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"
    STATUS_TIMEOUT = "timeout"

    STATUS_CHOICES = [
        (STATUS_PENDING, _("Pending")),
        (STATUS_OPEN, _("Open")),
        (STATUS_CLOSED, _("Closed")),
        (STATUS_TIMEOUT, _("Timeout")),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="help_requests",
        verbose_name=_("User"),
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        verbose_name=_("Status"),
    )
    message_text = models.TextField(blank=True, default="", verbose_name=_("Message"))
    admin_chat_message_id = models.BigIntegerField(null=True, blank=True, verbose_name=_("Admin chat message id"))
    media_message_ids = models.JSONField(default=list, blank=True, verbose_name=_("Media message ids"))
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_help_requests",
        verbose_name=_("Closed by"),
    )

    class Meta:
        db_table = "user_admin_help_request"
        ordering = ["-created_at"]
        verbose_name = _("Admin help request")
        verbose_name_plural = _("Admin help requests")

    def __str__(self) -> str:
        return f"AdminHelpRequest#{self.pk} user={self.user_id} status={self.status}"
