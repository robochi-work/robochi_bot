from types import SimpleNamespace
from typing import Any
from datetime import datetime
from django.utils import timezone
from service.notifications_impl import TelegramNotifier
from telegram.models import ChannelMessage
from .publisher import Observer
from ...tasks.resend import get_active_vacancies, resend_vacancies_to_channel


class VacancyTopResendChannelObserver(Observer):
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    def update(self, event: str, data: dict[str, Any]) -> None:
        vacancy = data['vacancy']
        if vacancy.members.count() >= vacancy.people_count:
            vacancy_message = ChannelMessage.objects.filter(
                extra__vacancy_id=vacancy.id,
            ).last()
            if vacancy_message:
                vacancies = get_active_vacancies()

                filtered_vacancies = []

                naive_now = datetime.now()
                aware_now = timezone.make_aware(naive_now, timezone.get_current_timezone())
                for v in vacancies:
                    if v.members.count() < v.people_count:
                        v_message = ChannelMessage.objects.filter(
                            extra__vacancy_id=v.id,
                        ).last()
                        if v_message and v_message.message_id < vacancy_message.message_id:

                            start_naive = datetime.combine(v.date, v.start_time)
                            start_aware = timezone.make_aware(start_naive, timezone.get_current_timezone())

                            if aware_now > start_aware:
                                if v.extra.get('start_pre_call') == 'need':
                                    filtered_vacancies.append(v)
                            else:
                                filtered_vacancies.append(v)

                resend_vacancies_to_channel(filtered_vacancies)