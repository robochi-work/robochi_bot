import logging
from typing import Any

from service.notifications_impl import TelegramNotifier

from ..call_formatter import CallVacancyTelegramTextFormatter
from .publisher import Observer

logger = logging.getLogger(__name__)


def _get_detail_markup(vacancy):
    from django.conf import settings
    from django.urls import reverse
    from telebot.types import InlineKeyboardMarkup

    from telegram.handlers.common import ButtonStorage

    markup = InlineKeyboardMarkup()
    markup.row(
        ButtonStorage.web_app(
            label="Керування вакансією",
            url=settings.BASE_URL.rstrip("/") + reverse("vacancy:detail", args=[vacancy.pk]),
        )
    )
    return markup


class VacancyApprovedUserObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data["vacancy"]
        is_resume = vacancy.first_rollcall_passed or vacancy.extra.get("sent_start_call", False)

        from telegram.handlers.bot_instance import bot

        # Повідомлення 2.2 — "Вашу вакансію схвалено"
        try:
            sent = bot.send_message(
                chat_id=vacancy.owner.id,
                text=(
                    "Повторний пошук розпочато."
                    if is_resume
                    else CallVacancyTelegramTextFormatter.vacancy_approved_user()
                ),
                reply_markup=_get_detail_markup(vacancy),
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
