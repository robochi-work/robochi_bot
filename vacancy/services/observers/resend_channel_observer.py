from typing import Any
from service.notifications_impl import TelegramNotifier
from telegram.models import ChannelMessage
from .publisher import Observer
from ...tasks.resend import resend_vacancy_to_channel


class VacancyTopResendChannelObserver(Observer):
    """When a vacancy fills up, republish other active vacancies that are below it in channel."""
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data['vacancy']
        filled_message = ChannelMessage.objects.filter(
            extra__vacancy_id=vacancy.id,
        ).last()
        if not filled_message:
            return

        from vacancy.models import Vacancy
        from vacancy.choices import STATUS_APPROVED, STATUS_ACTIVE

        other_vacancies = Vacancy.objects.filter(
            status__in=[STATUS_APPROVED, STATUS_ACTIVE],
            search_active=True,
        ).exclude(id=vacancy.id)

        for v in other_vacancies:
            v_message = ChannelMessage.objects.filter(
                extra__vacancy_id=v.id,
            ).last()
            if v_message and v_message.message_id < filled_message.message_id:
                resend_vacancy_to_channel(v)
