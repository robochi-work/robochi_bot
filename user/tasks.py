import logging
import time
from datetime import timedelta

from celery import shared_task
from django.db.models import Max
from django.utils import timezone

from telegram.handlers.bot_instance import bot

logger = logging.getLogger(__name__)

INACTIVE_DAYS = 180
UNREGISTERED_DAYS = 7
TELEGRAM_API_DELAY = 0.05


def check_telegram_deleted(telegram_id: int) -> bool:
    """Check if Telegram account is deleted. Returns True if deleted."""
    try:
        chat = bot.get_chat(telegram_id)
        first_name = getattr(chat, "first_name", "") or ""
        first_name = first_name.lower().strip()
        if not first_name or first_name in ["deleted account", "deleted"]:
            return True
        return False
    except Exception:
        return True


def get_last_worker_activity_date(user):
    """Get worker's last vacancy participation date."""
    from vacancy.models import VacancyUser

    result = VacancyUser.objects.filter(user=user).aggregate(last=Max("created_at"))
    last_date = result.get("last")

    if not last_date:
        last_date = user.date_joined

    return last_date


def get_last_employer_activity_date(user):
    """Get employer's last vacancy creation date."""
    from vacancy.models import Vacancy

    result = Vacancy.objects.filter(owner=user).aggregate(last=Max("date"))
    last_date = result.get("last")

    if last_date:
        last_date = timezone.make_aware(
            timezone.datetime.combine(last_date, timezone.datetime.min.time()),
            timezone.get_current_timezone(),
        )
    else:
        last_date = user.date_joined

    return last_date


@shared_task(name="user.tasks.cleanup_inactive_users_task")
def cleanup_inactive_users_task():
    """Daily task: delete users with deleted Telegram accounts and inactive workers/employers (180 days)."""
    from user.models import User
    from work.choices import WorkProfileRole

    cutoff = timezone.now() - timedelta(days=INACTIVE_DAYS)
    user_ids = list(User.objects.filter(is_staff=False, is_superuser=False).values_list("id", flat=True))

    deleted_count = 0
    inactive_count = 0
    total = len(user_ids)

    logger.info(f"Cleanup started: checking {total} users")

    for i, user_id in enumerate(user_ids):
        try:
            user = User.objects.select_related("work_profile").get(id=user_id)

            # 1. Check if Telegram account is deleted
            if user.telegram_id:
                if check_telegram_deleted(user.telegram_id):
                    username = user.username
                    user.delete()
                    deleted_count += 1
                    logger.info(f"Deleted user with deleted Telegram account: {user_id} (@{username})")
                    continue
                time.sleep(TELEGRAM_API_DELAY)

            # 2. Check inactivity (180 days) - workers and employers
            profile = getattr(user, "work_profile", None)
            if profile and profile.role == WorkProfileRole.WORKER:
                last_activity = get_last_worker_activity_date(user)
                if last_activity and last_activity < cutoff:
                    username = user.username
                    user.delete()
                    inactive_count += 1
                    logger.info(f"Deleted inactive worker: {user_id} (@{username}), last activity: {last_activity}")
                    continue

            if profile and profile.role == WorkProfileRole.EMPLOYER:
                last_activity = get_last_employer_activity_date(user)
                if last_activity and last_activity < cutoff:
                    username = user.username
                    user.delete()
                    inactive_count += 1
                    logger.info(f"Deleted inactive employer: {user_id} (@{username}), last activity: {last_activity}")

        except User.DoesNotExist:
            continue
        except Exception as e:
            logger.warning(f"Error checking user {user_id}: {e}")

        if (i + 1) % 500 == 0:
            logger.info(f"Cleanup progress: {i + 1}/{total}")

    logger.info(f"Cleanup complete: {deleted_count} deleted accounts removed, {inactive_count} inactive users removed")


@shared_task(name="user.tasks.cleanup_unregistered_users_task")
def cleanup_unregistered_users_task():
    """Daily task: delete users who pressed /start but never completed registration within 7 days."""
    from user.models import User

    cutoff = timezone.now() - timedelta(days=UNREGISTERED_DAYS)

    users = User.objects.filter(
        is_active=True,
        is_staff=False,
        is_superuser=False,
        date_joined__lt=cutoff,
    ).select_related("work_profile")

    count = 0
    for user in users:
        profile = getattr(user, "work_profile", None)
        if not profile or not profile.is_completed:
            username = user.username
            user_id = user.id
            user.delete()
            count += 1
            logger.info(f"Deleted unregistered user: {user_id} (@{username})")

    logger.info(f"Unregistered cleanup complete: {count} users removed")
