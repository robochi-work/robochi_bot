from types import SimpleNamespace
from typing import Any

from .publisher import Observer
from service.notifications import NotificationMethod
from service.notifications_impl import TelegramNotifier


class VacancyRenewalWorkersObserver(Observer):
    """
    Fires on VACANCY_APPROVED for renewal vacancies (pending_worker_renewal=True).
    Sends renewal poll to every current group member instead of publishing to channel.
    """

    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data['vacancy']
        if not vacancy.extra.get('pending_worker_renewal'):
            return

        from telegram.choices import CallStatus, CallType
        from vacancy.models import VacancyUserCall
        from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter
        from vacancy.services.call_markup import get_renewal_worker_markup

        members = vacancy.members.select_related('user')
        if not members.exists():
            return

        markup = get_renewal_worker_markup(vacancy)
        text = CallVacancyTelegramTextFormatter(vacancy).renewal_worker_ask()

        for vacancy_user in members:
            # Create VacancyUserCall record for tracking
            VacancyUserCall.objects.create(
                vacancy_user=vacancy_user,
                call_type=CallType.RENEWAL_WORKER.value,
                status=CallStatus.SENT.value,
            )
            self.notifier.notify(
                recipient=SimpleNamespace(chat_id=vacancy_user.user.id),
                method=NotificationMethod.TEXT,
                text=text,
                reply_markup=markup,
            )

        # Clear the flag — poll has been sent
        vacancy.extra['pending_worker_renewal'] = False
        vacancy.save(update_fields=['extra'])
