from typing import Iterable

from telegram.choices import CallStatus, CallType
from vacancy.models import Vacancy, VacancyUserCall


def create_vacancy_call(vacancy: Vacancy, status: CallStatus, call_type: CallType) -> Iterable[VacancyUserCall]:
    users_queryset = vacancy.members

    existing_calls = VacancyUserCall.objects.filter(vacancy_user__in=users_queryset, call_type=call_type)
    existing_map = [call.vacancy_user.id for call in existing_calls]
    missing_calls = []
    for vacancy_user in users_queryset:
        if vacancy_user.id not in existing_map:
            missing_calls.append(VacancyUserCall(
                vacancy_user=vacancy_user,
                status=status,
                call_type=call_type,
            ))
    if missing_calls:
        return VacancyUserCall.objects.bulk_create(missing_calls)
    return []