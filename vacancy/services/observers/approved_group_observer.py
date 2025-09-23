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