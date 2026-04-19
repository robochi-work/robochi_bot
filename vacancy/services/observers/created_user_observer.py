from types import SimpleNamespace
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

        faq_url = f"{settings.BASE_URL}/work/employer/faq/"
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton(
                text="Як це працює?",
                web_app=WebAppInfo(url=faq_url),
            )
        )

        self.notifier.notify(
            recipient=SimpleNamespace(
                chat_id=vacancy.owner.id,
            ),
            method=NotificationMethod.TEXT,
            text=CallVacancyTelegramTextFormatter.vacancy_created_user(),
            reply_markup=markup,
        )


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
