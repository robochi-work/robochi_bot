"""Management command: manually mark a vacancy as paid.

Usage:
    set -a && source .env && set +a
    python manage.py mark_vacancy_paid <vacancy_id> [--unblock]

The --unblock flag (default: True) lifts UNPAID/EMPLOYER_ROLLCALL_FAIL blocks
on the owner.
"""

from django.core.management.base import BaseCommand, CommandError

from user.choices import BlockReason
from user.models import UserBlock
from vacancy.choices import STATUS_PAID
from vacancy.models import Vacancy


class Command(BaseCommand):
    help = "Manually mark a vacancy as paid (for testing/admin use)."

    def add_arguments(self, parser):
        parser.add_argument("vacancy_id", type=int)
        parser.add_argument(
            "--keep-block",
            action="store_true",
            help="Do NOT lift the UNPAID/rollcall-fail block on the owner.",
        )

    def handle(self, *args, **options):
        vid = options["vacancy_id"]
        try:
            vacancy = Vacancy.objects.get(pk=vid)
        except Vacancy.DoesNotExist:
            raise CommandError(f"Vacancy #{vid} not found") from None

        if (vacancy.extra or {}).get("is_paid"):
            self.stdout.write(self.style.WARNING(f"Vacancy #{vid} is already paid."))
            return

        vacancy.extra = dict(vacancy.extra or {})
        vacancy.extra["is_paid"] = True
        vacancy.extra["paid_via_management_command"] = True
        vacancy.status = STATUS_PAID
        vacancy.save(update_fields=["extra", "status"])

        if not options["keep_block"]:
            lifted = UserBlock.objects.filter(
                user=vacancy.owner,
                is_active=True,
                reason__in=[BlockReason.UNPAID, BlockReason.EMPLOYER_ROLLCALL_FAIL],
            ).update(is_active=False)
            self.stdout.write(self.style.SUCCESS(f"Vacancy #{vid} marked as paid. Owner blocks lifted: {lifted}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Vacancy #{vid} marked as paid. Owner blocks kept."))
