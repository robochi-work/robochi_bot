import logging
from types import SimpleNamespace
from typing import Any

from service.notifications import NotificationMethod
from service.notifications_impl import TelegramNotifier

from ..call_formatter import CallVacancyTelegramTextFormatter
from ..call_markup import get_vacancy_my_list_markup
from .publisher import Observer

logger = logging.getLogger(__name__)


class VacancyApprovedUserObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data["vacancy"]

        # Повідомлення 2.2 — "Вашу вакансію схвалено" (залишаємо як є)
        self.notifier.notify(
            recipient=SimpleNamespace(
                chat_id=vacancy.owner.id,
            ),
            method=NotificationMethod.TEXT,
            text=CallVacancyTelegramTextFormatter.vacancy_approved_user(),
            reply_markup=get_vacancy_my_list_markup(),
        )

        # Повідомлення 2.3 — через 5 секунд надсилаємо посилання на групу з повторами
        from vacancy.tasks.employer_group_invite import send_employer_group_invite_task

        send_employer_group_invite_task.apply_async(
            args=[vacancy.id],
            countdown=5,
        )
