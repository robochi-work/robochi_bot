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
            import logging

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
            self._add_employer_to_group(vacancy)

    def _add_employer_to_group(self, vacancy) -> None:
        """Create a one-time invite link (no approval needed) and send it to the employer."""
        import logging

        from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

        from telegram.handlers.bot_instance import bot

        try:
            # Create one-time invite link without join request
            invite = bot.create_chat_invite_link(
                chat_id=vacancy.group.id,
                member_limit=1,
                creates_join_request=False,
                name=f"employer_{vacancy.owner.id}",
            )

            # Send invite to employer in bot chat
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton(
                    text="Перейти в групу вакансії",
                    url=invite.invite_link,
                )
            )

            bot.send_message(
                chat_id=vacancy.owner.id,
                text="Вашу вакансію схвалено! Перейдіть у групу для спілкування з робітниками:",
                reply_markup=markup,
            )
            logging.info(f"Employer {vacancy.owner.id} invite sent for group {vacancy.group.id}")
        except Exception as e:
            logging.warning(f"Failed to create employer invite for group {vacancy.group.id}: {e}")
