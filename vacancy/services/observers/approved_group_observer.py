import logging
from typing import Any

from service.notifications_impl import TelegramNotifier
from service.telegram_markup_factory import group_url_feedback_reply_markup

from ..vacancy_formatter import VacancyTelegramTextFormatter
from .publisher import Observer


class VacancyApprovedGroupObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data["vacancy"]
        sent_in_group = vacancy.extra.get("sent_in_group", None)
        if not sent_in_group:
            from telegram.handlers.bot_instance import bot

            try:
                message = bot.send_message(
                    chat_id=vacancy.group.id,
                    text=VacancyTelegramTextFormatter(vacancy).for_group(),
                    reply_markup=group_url_feedback_reply_markup(vacancy),
                    parse_mode="HTML",
                )
                if message:
                    try:
                        bot.pin_chat_message(
                            chat_id=vacancy.group.id,
                            message_id=message.message_id,
                            disable_notification=True,
                        )
                    except Exception as e:
                        logging.warning(f"Failed to pin message in group {vacancy.group.id}: {e}")
            except Exception as e:
                logging.warning(f"Failed to send message to group {vacancy.group.id}: {e}")

            vacancy.extra["sent_in_group"] = True
            vacancy.save(update_fields=["extra"])
