from typing import Literal, Optional, Iterable

from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _, override

from service.common import get_admin_url
from telegram.choices import CallStatus, CallType
from vacancy.models import Vacancy, VacancyUserCall


class CallVacancyTelegramTextFormatter:

    def __init__(self, vacancy: Vacancy):
        self.vacancy = vacancy

    @staticmethod
    def before_start_call() -> str:
        with override('uk'):
            return _(
                f'Work will start soon, confirm readiness within 20 minutes.'
            )

    @staticmethod
    def start_call() -> str:
        with override('uk'):
            return _(
                f'Please indicate the employees who showed up.'
            )

    def final_call(self) -> str:
        return self.start_call()

    def invoice_final_call_success(self) -> str:
        with override('uk'):
            return _('Payment for services to find manufacturers')

    def start_call_fail(self) -> str:
        with override('uk'):
            return _(
                f'Your employer marked you as a no-show for roll call.'
            ) + f'\n{self.vacancy.group.invite_link}'

    def admin_call_fail(self, call_type: CallType) -> str:
        users_call = VacancyUserCall.objects.filter(
            vacancy_user__in=self.vacancy.members,
            status=CallStatus.REJECT,
            call_type=call_type,
        )
        with override('uk'):
            return (
                _(f'The workers did not show up')
                + '\n'
                + '\n'.join([
                    f'{user_call.vacancy_user.user.phone_number} - <a href="{settings.BASE_URL.rstrip('/') + get_admin_url(user_call.vacancy_user.user)}">{user_call.vacancy_user.user.full_name or user_call.vacancy_user.user.id}</a>'
                    for user_call in users_call
                ])
                + '\n' + f'{self.vacancy.group.invite_link}'
            )

    def admin_start_call_fail(self) -> str:
        return self.admin_call_fail(call_type=CallType.START)

    def admin_after_start_call_fail(self) -> str:
        return self.admin_call_fail(call_type=CallType.AFTER_START)
