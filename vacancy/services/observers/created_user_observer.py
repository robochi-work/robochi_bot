from typing import Any

from django.utils.translation import gettext as _

from service.notifications import NotificationMethod
from service.notifications_impl import DjangoMessagesNotifier, TelegramNotifier

from ..call_formatter import CallVacancyTelegramTextFormatter
from .publisher import Observer


class VacancyCreatedUserObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data["vacancy"]
        from django.conf import settings
        from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

        from telegram.handlers.bot_instance import bot

        faq_url = f"{settings.BASE_URL}/work/employer/faq/"
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton(
                text="Як це працює?",
                web_app=WebAppInfo(url=faq_url),
            )
        )

        try:
            sent = bot.send_message(
                chat_id=vacancy.owner.id,
                text=CallVacancyTelegramTextFormatter.vacancy_created_user(),
                reply_markup=markup,
            )
            vacancy.extra = vacancy.extra or {}
            vacancy.extra["created_msg_id"] = sent.message_id
            vacancy.save(update_fields=["extra"])
        except Exception:
            import sentry_sdk

            sentry_sdk.capture_exception()


class VacancyCreatedUserDjangoObserver(Observer):
    def __init__(self, notifier: DjangoMessagesNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        request = data.get("request")

        if request:
            self.notifier.notify(
                recipient=request,
                method=NotificationMethod.TEXT,
                level="success",
                text=_("Your vacancy has been successfully created and sent for moderation!"),
            )
