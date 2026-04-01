import logging
import time
from datetime import timedelta

from celery import shared_task
from django.db.models import Max
from django.utils import timezone

from telegram.handlers.bot_instance import bot

logger = logging.getLogger(__name__)

INACTIVE_DAYS = 180
TELEGRAM_API_DELAY = 0.05  # 50ms between API calls (~20 req/sec, safe limit)


def check_telegram_deleted(telegram_id: int) -> bool:
    """Check if Telegram account is deleted. Returns True if deleted."""
    try:
        chat = bot.get_chat(telegram_id)
        first_name = getattr(chat, "first_name", "") or ""
        if first_name.lower().strip() in ["deleted account", "deleted"]:
            return True
        return False
    except Exception:
        return True


def get_last_activity_date(user):
    """Get user's last meaningful activity date."""
    from vacancy.models import Vacancy, VacancyUser
    from work.choices import WorkProfileRole

    profile = getattr(user, "work_profile", None)
    last_date = None

    if profile and profile.role == WorkProfileRole.WORKER:
        result = VacancyUser.objects.filter(user=user).aggregate(last=Max("created_at"))
        last_date = result.get("last")
    elif profile and profile.role == WorkProfileRole.EMPLOYER:
        result = Vacancy.objects.filter(owner=user).aggregate(last=Max("date"))
        last_date = result.get("last")
        if last_date:
            last_date = timezone.make_aware(
                timezone.datetime.combine(last_date, timezone.datetime.min.time()),
                timezone.get_current_timezone(),
            )

    if not last_date:
        last_date = user.date_joined

    return last_date


@shared_task
def cleanup_inactive_users_task():
    """Daily task: deactivate deleted Telegram accounts and inactive users (180 days)."""
    from user.models import User

    cutoff = timezone.now() - timedelta(days=INACTIVE_DAYS)
    user_ids = list(
        User.objects.filter(is_active=True, is_staff=False, is_superuser=False).values_list("id", flat=True)
    )

    deleted_count = 0
    inactive_count = 0
    total = len(user_ids)

    logger.info(f"Cleanup started: checking {total} users")

    for i, user_id in enumerate(user_ids):
        try:
            user = User.objects.get(id=user_id, is_active=True)

            # 1. Check if Telegram account is deleted
            if user.telegram_id:
                if check_telegram_deleted(user.telegram_id):
                    user.is_active = False
                    user.save(update_fields=["is_active"])
                    deleted_count += 1
                    logger.info(f"Deactivated deleted Telegram account: user {user.id} (@{user.username})")
                    continue
                time.sleep(TELEGRAM_API_DELAY)

            # 2. Check inactivity (180 days)
            last_activity = get_last_activity_date(user)
            if last_activity and last_activity < cutoff:
                user.is_active = False
                user.save(update_fields=["is_active"])
                inactive_count += 1
                logger.info(f"Deactivated inactive user: {user.id} (@{user.username}), last activity: {last_activity}")

        except User.DoesNotExist:
            continue
        except Exception as e:
            logger.warning(f"Error checking user {user.id}: {e}")

        # Progress log every 500 users
        if (i + 1) % 500 == 0:
            logger.info(f"Cleanup progress: {i + 1}/{total}")

    logger.info(f"Cleanup complete: {deleted_count} deleted accounts, {inactive_count} inactive users deactivated")
