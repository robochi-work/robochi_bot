import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="work.tasks.check_system_task")
def check_system_task():
    """Daily system integrity check — results sent to all staff admins via Telegram."""
    from service.broadcast_service import TelegramBroadcastService
    from service.notifications import NotificationMethod
    from service.notifications_impl import TelegramNotifier
    from telegram.handlers.bot_instance import bot
    from work.management.commands.check_system import run_checks

    results = run_checks()

    lines = ["<b>🔍 System integrity check</b>"]
    for result in results:
        icon = "✅" if result.ok else "❌"
        line = f"{icon} {result.label}"
        if not result.ok and result.detail:
            line += f"\n   <i>{result.detail[:200]}</i>"
        lines.append(line)

    fails = sum(1 for r in results if not r.ok)
    summary = "✅ All checks passed." if fails == 0 else f"❌ {fails} check(s) failed."
    lines.append(f"\n{summary}")

    text = "\n".join(lines)

    notifier = TelegramNotifier(bot)
    broadcast = TelegramBroadcastService(notifier)
    broadcast.admin_broadcast(method=NotificationMethod.TEXT, text=text)

    logger.info("check_system_task completed: %s", summary)


@shared_task(name="work.tasks.check_logs_task")
def check_logs_task():
    """Daily log analysis — results sent to all staff admins via Telegram."""
    from service.broadcast_service import TelegramBroadcastService
    from service.notifications import NotificationMethod
    from service.notifications_impl import TelegramNotifier
    from telegram.handlers.bot_instance import bot
    from work.management.commands.check_logs import run_log_analysis

    report = run_log_analysis()

    notifier = TelegramNotifier(bot)
    broadcast = TelegramBroadcastService(notifier)
    broadcast.admin_broadcast(method=NotificationMethod.TEXT, text=report)

    logger.info("check_logs_task completed")
