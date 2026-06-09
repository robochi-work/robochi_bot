import logging
import time
from datetime import timedelta

from celery import shared_task
from django.db.models import Max
from django.utils import timezone

from telegram.handlers.bot_instance import bot

logger = logging.getLogger(__name__)

INACTIVE_DAYS = 180
UNREGISTERED_DAYS = 1
TELEGRAM_API_DELAY = 0.05


def check_telegram_deleted(telegram_id: int) -> bool:
    """Check if Telegram account is deleted. Returns True if deleted.

    SAFETY: On ANY API error (rate limit, timeout, bot blocked, chat not found)
    we return False so the cleanup task does NOT delete a live user.
    Telegram errors are temporary; user deletion is irreversible and cascades
    to Vacancy (owner=CASCADE) and VacancyUser (user=CASCADE).
    """
    try:
        chat = bot.get_chat(telegram_id)
    except Exception as e:
        logger.warning(f"check_telegram_deleted: API error for {telegram_id}, skipping delete: {e}")
        return False
    first_name = getattr(chat, "first_name", "") or ""
    first_name = first_name.lower().strip()
    if not first_name or first_name in ["deleted account", "deleted"]:
        return True
    return False


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
    """Daily task: delete users who pressed /start but never completed registration within 1 day.

    By design these users have is_completed=False and no role/city → they
    cannot create vacancies or join vacancy groups. If a candidate for
    deletion DOES have such links, it indicates a data integrity bug
    elsewhere (e.g. wizard finished without setting is_completed=True).
    In that case we skip the deletion and alert admins for manual review,
    so no real user data is ever lost to a faulty cleanup.

    History: cleanup_inactive_users wiped @Nephrite_u (31.05) and
    @ParaibaUA (08.06) due to faulty Telegram API check; this is the
    related task hardened with the same fail-open philosophy.
    """
    from user.models import User
    from vacancy.models import Vacancy, VacancyUser

    cutoff = timezone.now() - timedelta(days=UNREGISTERED_DAYS)

    users = User.objects.filter(
        is_active=True,
        is_staff=False,
        is_superuser=False,
        date_joined__lt=cutoff,
    ).select_related("work_profile")

    deleted = 0
    anomalies = []  # users we refused to delete due to unexpected links

    for user in users:
        profile = getattr(user, "work_profile", None)
        if profile and profile.is_completed:
            continue  # fully registered

        # Anomaly guard: an unregistered user should have NO vacancy links.
        # If they do, something else in the code is leaving is_completed=False
        # for a real user. Refuse deletion and alert admins.
        owned = Vacancy.objects.filter(owner=user).count()
        vu_links = VacancyUser.objects.filter(user=user).count()
        if owned or vu_links:
            anomalies.append(
                {
                    "user_id": user.id,
                    "username": user.username,
                    "phone_number": user.phone_number,
                    "role": getattr(profile, "role", None),
                    "vacancies_owned": owned,
                    "vacancy_user_links": vu_links,
                }
            )
            logger.warning(
                f"Cleanup ANOMALY (skip+alert): unregistered user has vacancy data — "
                f"user_id={user.id} @{user.username} phone={user.phone_number} "
                f"role={getattr(profile, 'role', None)} "
                f"owned_vacancies={owned} vacancy_user_links={vu_links}"
            )
            continue

        # Pre-delete diagnostic log
        logger.info(
            f"Deleting unregistered user: user_id={user.id} @{user.username} "
            f"phone={user.phone_number} "
            f"date_joined={user.date_joined.isoformat()} "
            f"has_profile={profile is not None} "
            f"role={getattr(profile, 'role', None)} "
            f"is_completed={getattr(profile, 'is_completed', None)}"
        )
        user.delete()
        deleted += 1

    logger.info(f"Unregistered cleanup complete: {deleted} users removed, {len(anomalies)} anomalies")

    # Alert admins about anomalies — they signal a data bug elsewhere
    if anomalies:
        try:
            from service.broadcast_service import TelegramBroadcastService
            from service.notifications_impl import TelegramNotifier
            from telegram.handlers.bot_instance import bot

            lines = ["⚠️ Cleanup anomaly: незареєстровані юзери з вакансіями (НЕ видалені):"]
            for a in anomalies:
                lines.append(
                    f"• user_id={a['user_id']} @{a['username']} "
                    f"phone={a['phone_number']} role={a['role']} "
                    f"owned={a['vacancies_owned']} vu_links={a['vacancy_user_links']}"
                )
            lines.append("Потрібне ручне розслідування — десь is_completed=True не виставлено.")
            broadcast = TelegramBroadcastService(notifier=TelegramNotifier(bot))
            broadcast.admin_broadcast(text="\n".join(lines))
        except Exception as e:
            logger.error(f"Failed to send cleanup anomaly alert: {e}")
