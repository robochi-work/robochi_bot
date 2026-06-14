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


# Status constants returned by check_telegram_status
TG_STATUS_ALIVE = "alive"  # account works, normal user
TG_STATUS_DELETED = "deleted"  # Telegram account was deleted (sure)
TG_STATUS_BOT_BLOCKED = "bot_blocked"  # user blocked the bot — block in our system, do NOT delete
TG_STATUS_UNKNOWN = "unknown"  # transient API error or no data — DO NOTHING


def _check_via_channel(user):
    """Step 1 — check via city channel where bot is admin.

    Returns one of TG_STATUS_* or None if cannot determine (no city, no channel,
    user not subscribed, API error).
    """
    profile = getattr(user, "work_profile", None)
    if not profile or not profile.city:
        return None
    from telegram.models import Channel

    channel = Channel.objects.filter(city=profile.city).first()
    if not channel:
        return None

    try:
        member = bot.get_chat_member(channel.id, user.id)
    except Exception as e:
        logger.warning(f"_check_via_channel: API error user_id={user.id} channel={channel.id}: {e}")
        return None

    status = getattr(member, "status", "")
    member_user = getattr(member, "user", None)
    first_name = ""
    if member_user is not None:
        first_name = (getattr(member_user, "first_name", "") or "").lower().strip()

    if status not in ("left", "kicked"):
        if not first_name or first_name in ("deleted account", "deleted"):
            return TG_STATUS_DELETED
        return TG_STATUS_ALIVE

    # left/kicked — cannot tell from channel alone (non-subscribers also look like this)
    return None


def _check_via_private_chat(user_id: int) -> str:
    """Step 2 — check via private chat with the bot. Returns one of TG_STATUS_*."""
    try:
        chat = bot.get_chat(user_id)
    except Exception as e:
        msg = str(e).lower()
        if "blocked" in msg or "chat not found" in msg or "forbidden" in msg:
            logger.info(f"_check_via_private_chat: user_id={user_id} bot is blocked or no chat: {e}")
            return TG_STATUS_BOT_BLOCKED
        logger.warning(f"_check_via_private_chat: API error user_id={user_id}: {e}")
        return TG_STATUS_UNKNOWN

    first_name = (getattr(chat, "first_name", "") or "").lower().strip()
    if not first_name or first_name in ("deleted account", "deleted"):
        return TG_STATUS_DELETED
    return TG_STATUS_ALIVE


def check_telegram_status(user) -> str:
    """Combined Telegram-account status check.

    Returns TG_STATUS_ALIVE / TG_STATUS_DELETED / TG_STATUS_BOT_BLOCKED / TG_STATUS_UNKNOWN.

    Strategy:
        1) If user has city, try city channel. Works even if user blocked the bot.
        2) Otherwise fall back to private chat.

    On any unrecognised API error → TG_STATUS_UNKNOWN (fail-open).
    """
    channel_result = _check_via_channel(user)
    if channel_result in (TG_STATUS_ALIVE, TG_STATUS_DELETED):
        return channel_result
    return _check_via_private_chat(user.id)


@shared_task(name="user.tasks.cleanup_inactive_users_task")
def cleanup_inactive_users_task():
    """Daily task at 03:00. Three responsibilities, all fail-open.

    Pass 0 (re-evaluate existing BOT_BLOCKED holders):
        ALIVE   → user unblocked the bot → remove the block.
        DELETED → Telegram account was deleted → delete the user (the
                  block is removed automatically via CASCADE).
        BOT_BLOCKED / UNKNOWN → keep the block.

    Pass 1 (every regular user):
        DELETED     → delete (positive evidence required from channel or chat).
        BOT_BLOCKED → create an indefinite temporary block (blocked_until=None).
                      The block is auto-released next time check finds the user
                      ALIVE (handled in Pass 0). User is NOT deleted — they
                      simply can\'t receive system messages while bot is blocked.
        UNKNOWN     → skip this round.
        ALIVE       → fall through to the 180-day inactivity check.

    History: 31.05 @Nephrite_u and 08.06 @ParaibaUA were wrongly deleted
    by an over-eager fail-closed Telegram API check. Everything here is
    fail-open: when in doubt — do nothing.
    """
    from user.choices import BlockReason, BlockType
    from user.models import User, UserBlock
    from user.services import BlockService
    from work.choices import WorkProfileRole

    # ── Pass 0: re-evaluate existing BOT_BLOCKED blocks ───────────────────
    active_bot_blocks = list(
        UserBlock.objects.filter(
            is_active=True,
            reason=BlockReason.BOT_BLOCKED,
        ).select_related("user", "user__work_profile", "user__work_profile__city")
    )

    auto_unblocked = 0
    bot_blocked_deleted = 0
    for block in active_bot_blocks:
        status = check_telegram_status(block.user)
        time.sleep(TELEGRAM_API_DELAY)

        if status == TG_STATUS_ALIVE:
            BlockService.unblock_user(block.id)
            auto_unblocked += 1
            logger.info(f"Auto-unblock: bot is no longer blocked by user_id={block.user_id} @{block.user.username}")
        elif status == TG_STATUS_DELETED:
            uid = block.user_id
            username = block.user.username
            block.user.delete()
            bot_blocked_deleted += 1
            logger.info(f"Deleted (was bot-blocked, now Telegram-deleted): {uid} (@{username})")
        # BOT_BLOCKED or UNKNOWN — keep the block

    # ── Pass 1: scan every regular user ───────────────────────────────────
    cutoff = timezone.now() - timedelta(days=INACTIVE_DAYS)
    user_ids = list(User.objects.filter(is_staff=False, is_superuser=False).values_list("id", flat=True))

    deleted_count = 0
    inactive_count = 0
    blocked_count = 0
    total = len(user_ids)

    logger.info(f"Cleanup started: re-evaluated {len(active_bot_blocks)} bot-blocked, now checking {total} users")

    for i, user_id in enumerate(user_ids):
        try:
            user = User.objects.select_related("work_profile", "work_profile__city").get(id=user_id)

            status = check_telegram_status(user)
            time.sleep(TELEGRAM_API_DELAY)

            if status == TG_STATUS_DELETED:
                username = user.username
                user.delete()
                deleted_count += 1
                logger.info(f"Deleted user with deleted Telegram account: {user_id} (@{username})")
                continue

            if status == TG_STATUS_BOT_BLOCKED:
                already_blocked = user.blocks.filter(is_active=True, reason=BlockReason.BOT_BLOCKED).exists()
                if not already_blocked:
                    BlockService.block_user(
                        user=user,
                        block_type=BlockType.TEMPORARY,
                        reason=BlockReason.BOT_BLOCKED,
                        blocked_until=None,  # indefinite — auto-released on next ALIVE check
                        comment="Бот заблокований користувачем (виявлено автоматично)",
                    )
                    blocked_count += 1
                    logger.info(f"Temp-blocked (indefinite, bot blocked): {user_id} (@{user.username})")
                continue

            if status == TG_STATUS_UNKNOWN:
                logger.info(f"Cleanup skip (unknown TG status): user_id={user_id} @{user.username}")
                continue

            # status == TG_STATUS_ALIVE → check 180-day inactivity
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

    logger.info(
        f"Cleanup complete: {deleted_count} TG-deleted, "
        f"{inactive_count} inactive removed, "
        f"{blocked_count} newly bot-blocked, "
        f"{auto_unblocked} auto-unblocked, "
        f"{bot_blocked_deleted} bot-blocked + TG-deleted"
    )


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


@shared_task(name="user.tasks.cleanup_stale_admin_help")
def cleanup_stale_admin_help_task(req_id):
    """Через 10 хв після start_request:
    якщо юзер не відправив повідомлення — видаляємо запит «Опишіть проблему»
    та переводимо заявку в TIMEOUT."""
    from django.core.cache import cache
    from django.utils import timezone

    from telegram.handlers.bot_instance import get_bot
    from user.models import AdminHelpRequest
    from user.services.admin_help import CACHE_KEY

    try:
        req = AdminHelpRequest.objects.get(id=req_id)
    except AdminHelpRequest.DoesNotExist:
        return

    if req.status != AdminHelpRequest.STATUS_PENDING:
        return

    user_id = req.user_id
    pending_msg_id = cache.get(f"admin_help_pending_msg:{user_id}")
    if pending_msg_id:
        try:
            get_bot().delete_message(user_id, pending_msg_id)
        except Exception:
            pass
        cache.delete(f"admin_help_pending_msg:{user_id}")

    cache.delete(CACHE_KEY.format(user_id=user_id))

    req.status = AdminHelpRequest.STATUS_TIMEOUT
    req.closed_at = timezone.now()
    req.save(update_fields=["status", "closed_at"])


@shared_task(name="user.tasks.auto_close_admin_help")
def auto_close_admin_help_task():
    """Авто-закриття OPEN-заявок старіше 24 годин.
    Запускається celery-beat раз на годину."""
    from django.utils import timezone

    from user.models import AdminHelpRequest

    threshold = timezone.now() - timedelta(hours=24)
    qs = AdminHelpRequest.objects.filter(
        status=AdminHelpRequest.STATUS_OPEN,
        created_at__lt=threshold,
    )
    count = qs.update(status=AdminHelpRequest.STATUS_CLOSED, closed_at=timezone.now())
    if count:
        logging.getLogger(__name__).info(f"auto_close_admin_help: closed {count} stale requests")
