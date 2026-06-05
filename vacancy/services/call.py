from collections.abc import Iterable

from telegram.choices import CallStatus, CallType
from vacancy.models import Vacancy, VacancyUserCall


def create_vacancy_call(vacancy: Vacancy, status: CallStatus, call_type: CallType) -> Iterable[VacancyUserCall]:
    users_queryset = vacancy.members

    existing_calls = VacancyUserCall.objects.filter(vacancy_user__in=users_queryset, call_type=call_type)
    existing_map = [call.vacancy_user.id for call in existing_calls]
    missing_calls = []
    for vacancy_user in users_queryset:
        if vacancy_user.id not in existing_map:
            missing_calls.append(
                VacancyUserCall(
                    vacancy_user=vacancy_user,
                    status=status,
                    call_type=call_type,
                )
            )
    if missing_calls:
        return VacancyUserCall.objects.bulk_create(missing_calls)
    return []


def reset_before_start_cycle(vacancy):
    """Mark the start of a NEW 2h-before-start notification cycle.

    Called whenever the vacancy is (re)submitted for the regular flow:
    initial creation, resume_search after STOP, renewal for tomorrow,
    admin moderation. The flag stops the next Celery tick from re-sending
    the 2h notice; the anchor lets the filter compare against the value
    the worker should actually expect.

    Do NOT call from continue_search — that is the SAME cycle (quick
    re-publish to top up workers), not a new one.
    """
    from datetime import datetime as _dt

    from django.utils import timezone as _tz

    start_naive = _dt.combine(vacancy.date, vacancy.start_time)
    start_aware = _tz.make_aware(start_naive, _tz.get_current_timezone())
    if not vacancy.extra:
        vacancy.extra = {}
    vacancy.extra["original_start_datetime"] = start_aware.isoformat()
    vacancy.extra.pop("pre_call_done", None)
    vacancy.save(update_fields=["extra"])
