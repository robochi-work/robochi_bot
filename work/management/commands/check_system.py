import logging
from typing import NamedTuple

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.urls import reverse

logger = logging.getLogger(__name__)

REQUIRED_BEAT_TASKS = [
    "test_heartbeat",
    "before_start_call_task",
    "after_first_call_check_task",
    "start_call_check_task",
    "final_call_check_task",
    "close_vacancy_task",
    "close_lifecycle_timer_task",
    "worker_join_confirm_check_task",
    "resend_vacancies_to_channel_task",
    "cleanup_inactive_users",
    "renewal_offer_task",
    "renewal_worker_check_task",
    "check_system",
    "check_logs",
]


class CheckResult(NamedTuple):
    ok: bool
    label: str
    detail: str = ""


def _check_channels() -> CheckResult:
    from telegram.models import Channel

    bad = Channel.objects.filter(Q(invite_link__isnull=True) | Q(invite_link="") | Q(has_bot_administrator=False))
    if bad.exists():
        ids = list(bad.values_list("id", flat=True)[:10])
        return CheckResult(
            False,
            "Channels: invite_link + has_bot_administrator",
            f"{bad.count()} channel(s) missing invite_link or bot admin: {ids}",
        )
    return CheckResult(True, "Channels: invite_link + has_bot_administrator")


def _check_groups() -> CheckResult:
    from telegram.models import Group

    bad = Group.objects.filter(status=Group.STATUS_AVAILABLE).filter(Q(invite_link__isnull=True) | Q(invite_link=""))
    if bad.exists():
        ids = list(bad.values_list("id", flat=True)[:10])
        return CheckResult(
            False,
            "Groups (available): invite_link",
            f"{bad.count()} available group(s) without invite_link: {ids}",
        )
    return CheckResult(True, "Groups (available): invite_link")


def _check_vacancy_user_orphans() -> CheckResult:
    from vacancy.models import VacancyUser

    orphans = VacancyUser.objects.filter(vacancy__isnull=True)
    if orphans.exists():
        return CheckResult(
            False,
            "VacancyUser orphans",
            f"{orphans.count()} VacancyUser record(s) without a linked Vacancy",
        )
    return CheckResult(True, "VacancyUser orphans")


def _check_approved_vacancies() -> CheckResult:
    from vacancy.models import Vacancy

    bad = Vacancy.objects.filter(status=Vacancy.STATUS_APPROVED).filter(Q(group__isnull=True) | Q(channel__isnull=True))
    if bad.exists():
        ids = list(bad.values_list("id", flat=True)[:10])
        return CheckResult(
            False,
            "Approved vacancies: group + channel assigned",
            f"{bad.count()} approved vacancy/vacancies without group or channel: {ids}",
        )
    return CheckResult(True, "Approved vacancies: group + channel assigned")


def _check_observer_subscriptions() -> CheckResult:
    errors = []
    for module in (
        "vacancy.services.observers.subscriber_setup",
        "work.service.subscriber_setup",
    ):
        try:
            __import__(module)
        except Exception as exc:
            errors.append(f"{module}: {exc}")
    if errors:
        return CheckResult(False, "Observer subscriptions", "; ".join(errors))
    return CheckResult(True, "Observer subscriptions")


def _check_celery_beat() -> CheckResult:
    try:
        from config.settings.celery import app

        schedule = app.conf.beat_schedule or {}
        missing = [t for t in REQUIRED_BEAT_TASKS if t not in schedule]
        if missing:
            return CheckResult(
                False,
                "Celery beat schedule",
                f"Missing task(s): {missing}",
            )
        return CheckResult(True, "Celery beat schedule")
    except Exception as exc:
        return CheckResult(False, "Celery beat schedule", f"Failed to load schedule: {exc}")


def _check_webhook_url() -> CheckResult:
    try:
        from telegram.handlers.bot_instance import bot

        expected = settings.BASE_URL + reverse("telegram:telegram_webhook")
        info = bot.get_webhook_info()
        actual = info.url or ""
        if actual != expected:
            return CheckResult(
                False,
                "Webhook URL",
                f"expected={expected!r}, actual={actual!r}",
            )
        return CheckResult(True, "Webhook URL")
    except Exception as exc:
        return CheckResult(False, "Webhook URL", f"Error: {exc}")


def run_checks() -> list[CheckResult]:
    return [
        _check_channels(),
        _check_groups(),
        _check_vacancy_user_orphans(),
        _check_approved_vacancies(),
        _check_observer_subscriptions(),
        _check_celery_beat(),
        _check_webhook_url(),
    ]


class Command(BaseCommand):
    help = "Check system integrity: channels, groups, vacancies, observers, Celery beat, webhook"

    def handle(self, *args, **options):
        self.stdout.write("Running system integrity checks...\n")
        results = run_checks()
        all_ok = True
        for result in results:
            if result.ok:
                self.stdout.write(f"✅ OK   {result.label}")
            else:
                all_ok = False
                self.stdout.write(self.style.ERROR(f"❌ FAIL {result.label}: {result.detail}"))

        self.stdout.write("")
        if all_ok:
            self.stdout.write(self.style.SUCCESS("All checks passed."))
        else:
            fails = sum(1 for r in results if not r.ok)
            self.stdout.write(self.style.ERROR(f"{fails} check(s) failed."))
