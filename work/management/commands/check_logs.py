import json
import logging
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

LOGS_DIR = Path(__file__).resolve().parents[4] / "logs"
LOG_FILES = ["django.log", "bot.log", "celery.log", "business.log", "errors.log"]


def _count_levels_in_text_log(path: Path, since: datetime) -> dict:
    """Count ERROR/WARNING lines in a plain-text log file written after `since`."""
    counts = {"ERROR": 0, "WARNING": 0}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                # Lines start with [YYYY-MM-DD HH:MM:SS]
                if line.startswith("["):
                    try:
                        ts_str = line[1:20]
                        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                        if ts < since:
                            continue
                    except ValueError:
                        pass
                if " ERROR " in line:
                    counts["ERROR"] += 1
                elif " WARNING " in line:
                    counts["WARNING"] += 1
    except FileNotFoundError:
        pass
    return counts


def _parse_errors_log(path: Path, since: datetime) -> list[dict]:
    """Parse JSON-formatted errors.log and return entries newer than `since`."""
    entries = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    ts_str = record.get("asctime", "")
                    # Format: "2026-04-01T06:44:07"
                    try:
                        ts = datetime.fromisoformat(ts_str)
                    except ValueError:
                        ts = datetime.min
                    if ts >= since:
                        entries.append(record)
                except json.JSONDecodeError:
                    pass
    except FileNotFoundError:
        pass
    return entries


def run_log_analysis() -> str:
    """
    Analyse logs for the last 24 hours.
    Returns a formatted HTML report string for Telegram.
    """
    since = datetime.now() - timedelta(hours=24)
    lines = ["<b>📊 Log report (last 24h)</b>"]

    # --- Per-file ERROR/WARNING counts ---
    lines.append("")
    lines.append("<b>File summary:</b>")
    total_errors = 0
    total_warnings = 0

    for filename in LOG_FILES:
        path = LOGS_DIR / filename
        if not path.exists():
            continue

        if filename == "errors.log":
            entries = _parse_errors_log(path, since)
            errors = sum(1 for e in entries if e.get("levelname") == "ERROR")
            warnings = sum(1 for e in entries if e.get("levelname") == "WARNING")
        else:
            counts = _count_levels_in_text_log(path, since)
            errors = counts["ERROR"]
            warnings = counts["WARNING"]

        total_errors += errors
        total_warnings += warnings

        if errors or warnings:
            lines.append(f"  <code>{filename}</code>: {errors} ERR / {warnings} WARN")

    lines.append(f"<b>Total: {total_errors} errors, {total_warnings} warnings</b>")

    # --- Top-5 errors from errors.log grouped by logger name ---
    errors_log_path = LOGS_DIR / "errors.log"
    entries = _parse_errors_log(errors_log_path, since)
    error_entries = [e for e in entries if e.get("levelname") == "ERROR"]

    if error_entries:
        lines.append("")
        lines.append("<b>Top-5 error sources (by logger):</b>")
        name_counter: Counter = Counter(e.get("name", "unknown") for e in error_entries)
        for name, count in name_counter.most_common(5):
            lines.append(f"  {count}× <code>{name}</code>")

        lines.append("")
        lines.append("<b>Top-5 most frequent errors (by message):</b>")
        msg_counter: Counter = Counter((e.get("message") or "")[:120] for e in error_entries)
        for msg, count in msg_counter.most_common(5):
            safe_msg = msg.replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f"  {count}× <i>{safe_msg}</i>")

    if total_errors == 0 and total_warnings == 0:
        lines.append("")
        lines.append("✅ No errors or warnings in the last 24 hours.")

    return "\n".join(lines)


class Command(BaseCommand):
    help = "Analyse log files for the last 24 hours and report to admins via Telegram"

    def handle(self, *args, **options):
        report = run_log_analysis()
        self.stdout.write(report)

        from service.broadcast_service import TelegramBroadcastService
        from service.notifications import NotificationMethod
        from service.notifications_impl import TelegramNotifier
        from telegram.handlers.bot_instance import bot

        notifier = TelegramNotifier(bot)
        broadcast = TelegramBroadcastService(notifier)
        broadcast.admin_broadcast(method=NotificationMethod.TEXT, text=report)
        self.stdout.write(self.style.SUCCESS("Report sent to admins."))
