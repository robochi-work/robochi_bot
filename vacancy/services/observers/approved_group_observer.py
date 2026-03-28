from types import SimpleNamespace
from typing import Any
from django.utils.translation import gettext as _
from service.notifications import NotificationMethod
from service.notifications_impl import TelegramNotifier
from service.telegram_markup_factory import group_url_feedback_reply_markup
from telegram.models import Channel
from .publisher import Observer
from ..vacancy_formatter import VacancyTelegramTextFormatter


class VacancyApprovedGroupObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data['vacancy']
        sent_in_group = vacancy.extra.get('sent_in_group', None)
        if not sent_in_group:
            self.notifier.notify(
                recipient=SimpleNamespace(chat_id=vacancy.group.id,),
                method=NotificationMethod.TEXT,
                text=VacancyTelegramTextFormatter(vacancy).for_group(),
                reply_markup=group_url_feedback_reply_markup(vacancy),
                vacancy=vacancy,
            )
            vacancy.extra['sent_in_group'] = True
            vacancy.save(update_fields=['extra'])

            # Auto-add employer to the vacancy group
            self._add_employer_to_group(vacancy)

    def _add_employer_to_group(self, vacancy) -> None:
        """Create a one-time invite link (no approval needed) and send it to the employer."""
        import logging
        from telegram.handlers.bot_instance import bot
        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

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
            markup.add(InlineKeyboardButton(
                text="Перейти в групу вакансії",
                url=invite.invite_link,
            ))

            bot.send_message(
                chat_id=vacancy.owner.id,
                text="Вашу вакансію схвалено! Перейдіть у групу для спілкування з робітниками:",
                reply_markup=markup,
            )
            logging.info(f"Employer {vacancy.owner.id} invite sent for group {vacancy.group.id}")
        except Exception as e:
            logging.warning(f"Failed to create employer invite for group {vacancy.group.id}: {e}")