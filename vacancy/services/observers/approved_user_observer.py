import logging
from typing import Any

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

        from telegram.handlers.bot_instance import bot

        # Повідомлення 2.2 — "Вашу вакансію схвалено"
        try:
            sent = bot.send_message(
                chat_id=vacancy.owner.id,
                text=CallVacancyTelegramTextFormatter.vacancy_approved_user(),
                reply_markup=get_vacancy_my_list_markup(),
            )
            vacancy.extra = vacancy.extra or {}
            vacancy.extra["approved_msg_id"] = sent.message_id
            vacancy.save(update_fields=["extra"])
        except Exception:
            import sentry_sdk

            sentry_sdk.capture_exception()

        # Повідомлення 2.3 — через 5 секунд надсилаємо посилання на групу з повторами
        from vacancy.tasks.employer_group_invite import send_employer_group_invite_task

        send_employer_group_invite_task.apply_async(
            args=[vacancy.id],
            countdown=5,
        )
