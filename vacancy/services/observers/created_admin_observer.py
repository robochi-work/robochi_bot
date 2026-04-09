import logging
from typing import Any

from service.telegram_markup_factory import admin_vacancy_reply_markup
from vacancy.services.vacancy_formatter import VacancyTelegramTextFormatter

from .publisher import Observer

logger = logging.getLogger(__name__)


class VacancyCreatedAdminObserver(Observer):
    def __init__(self, notifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data["vacancy"]
        from user.models import User

        admin_ids = list(User.objects.filter(is_staff=True).values_list("id", flat=True))
        admin_messages = {}
        for admin_id in admin_ids:
            try:
                msg = self.notifier.bot.send_message(
                    admin_id,
                    VacancyTelegramTextFormatter(vacancy).for_admin_chat(),
                    reply_markup=admin_vacancy_reply_markup(vacancy),
                    parse_mode="HTML",
                )
                if msg:
                    admin_messages[str(admin_id)] = msg.message_id
            except Exception:
                logger.exception("Failed to send moderation msg to admin %s", admin_id)
        if admin_messages:
            if not vacancy.extra:
                vacancy.extra = {}
            vacancy.extra["admin_moderation_messages"] = admin_messages
            vacancy.save(update_fields=["extra"])
