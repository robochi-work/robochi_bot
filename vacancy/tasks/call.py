import logging
from typing import Iterable, NewType
from datetime import timedelta, datetime, date
from django.utils import timezone
from celery import shared_task

from django.db import connection
from telegram.choices import CallStatus, CallType
from telegram.service.group import GroupService
from vacancy.choices import STATUS_ACTIVE, STATUS_APPROVED, STATUS_CLOSED
from vacancy.models import Vacancy, VacancyUserCall
from vacancy.services.observers.call_observer import VacancyBeforeCallObserver
from vacancy.services.observers.events import VACANCY_BEFORE_CALL, VACANCY_START_CALL, VACANCY_AFTER_START_CALL, \
    VACANCY_CLOSE, VACANCY_CLOSE_PAYMENT_DOES_NOT_EXIST
from vacancy.services.observers.subscriber_setup import telegram_notifier, vacancy_publisher

Minutes = int
logger = logging.getLogger(__name__)


def get_before_start_vacancies(delay: Minutes = 120) -> Iterable[Vacancy]:
    vacancies = Vacancy.objects.filter(
        status__in=[STATUS_ACTIVE, STATUS_APPROVED],
        date=date.today(),
    )

    naive_now = datetime.now()
    aware_now = timezone.make_aware(naive_now, timezone.get_current_timezone())
    filtered_vacancies = []
    for vacancy in vacancies:
        start_naive = datetime.combine(vacancy.date, vacancy.start_time)
        start_aware = timezone.make_aware(start_naive, timezone.get_current_timezone())

        before_start_time = start_aware - timedelta(minutes=delay)
        if before_start_time < aware_now < start_aware:
            filtered_vacancies.append(vacancy)
    return filtered_vacancies


def get_start_vacancies(delay: Minutes = 10) -> Iterable[Vacancy]:
    vacancies = Vacancy.objects.filter(
        status__in=[STATUS_ACTIVE, STATUS_APPROVED],
        date=date.today(),
    )

    naive_now = datetime.now()
    aware_now = timezone.make_aware(naive_now, timezone.get_current_timezone())
    filtered_vacancies = []
    for vacancy in vacancies:
        start_naive = datetime.combine(vacancy.date, vacancy.start_time)
        start_aware = timezone.make_aware(start_naive, timezone.get_current_timezone())

        after_start_time = start_aware + timedelta(minutes=delay)
        if after_start_time > aware_now > start_aware:
            filtered_vacancies.append(vacancy)
    return filtered_vacancies


def get_final_vacancies() -> Iterable[Vacancy]:
    vacancies = Vacancy.objects.filter(
        status__in=[STATUS_ACTIVE, STATUS_APPROVED],
        date=date.today(),
    )

    naive_now = datetime.now()
    aware_now = timezone.make_aware(naive_now, timezone.get_current_timezone())
    filtered_vacancies = []
    for vacancy in vacancies:
        end_naive = datetime.combine(vacancy.date, vacancy.end_time)
        end_aware = timezone.make_aware(end_naive, timezone.get_current_timezone())

        if aware_now > end_aware:
            filtered_vacancies.append(vacancy)
    return filtered_vacancies


def before_start_call(vacancies: Iterable[Vacancy]):
    for vacancy in vacancies:
        vacancy_publisher.notify(VACANCY_BEFORE_CALL, data={'vacancy': vacancy})


def after_first_call_check(vacancies: Iterable[Vacancy], delay: Minutes = 20):
    for vacancy in vacancies:
        calls = VacancyUserCall.objects.filter(vacancy_user__in=vacancy.members, call_type=CallType.AFTER_START)
        for call in calls:
            if timezone.now() - call.created_at > timedelta(minutes=delay):
                if not call.status == CallStatus.CONFIRM:
                    try:
                        GroupService.kick_user(
                            chat_id=call.vacancy_user.vacancy.group.id,
                            user_id=call.vacancy_user.user.id,
                        )
                    except Exception as e:
                        ...


def start_call_check(vacancies: Iterable[Vacancy]):
    for vacancy in vacancies:
        sent_start_call = vacancy.extra.get('sent_start_call', False)
        if not sent_start_call:
            vacancy_publisher.notify(VACANCY_START_CALL, data={'vacancy': vacancy})
            vacancy.extra['sent_start_call'] = True
            vacancy.save(update_fields=['extra'])


def final_call_check(vacancies: Iterable[Vacancy]):
    for vacancy in vacancies:
        sent_final_call = vacancy.extra.get('sent_final_call', False)
        if not sent_final_call:
            vacancy_publisher.notify(VACANCY_AFTER_START_CALL, data={'vacancy': vacancy})
            vacancy.extra['sent_final_call'] = True
            vacancy.save(update_fields=['extra'])


def close_vacancy(vacancy: Vacancy):
    if not vacancy.extra.get('payment_checked', False):
        if vacancy.extra.get('is_paid', False):
            vacancy_publisher.notify(VACANCY_CLOSE, data={'vacancy': vacancy})
        else:
            vacancy_publisher.notify(VACANCY_CLOSE_PAYMENT_DOES_NOT_EXIST, data={'vacancy': vacancy})

        vacancy.extra['payment_checked'] = True
        vacancy.save(update_fields=['extra'])



@shared_task
def before_start_call_task():
    connection.close()
    vacancies = get_before_start_vacancies()
    before_start_call(vacancies=vacancies)


@shared_task
def after_first_call_check_task(delay: Minutes = 20):
    connection.close()
    vacancies = get_before_start_vacancies()
    after_first_call_check(vacancies=vacancies, delay=delay)


@shared_task
def start_call_check_task():
    connection.close()
    vacancies = get_start_vacancies()
    start_call_check(vacancies=vacancies)


@shared_task
def final_call_check_task():
    connection.close()
    vacancies = get_final_vacancies()
    final_call_check(vacancies=vacancies)


@shared_task
def close_vacancy_task(delay: Minutes = 120):
    connection.close()
    vacancies = get_final_vacancies()
    for vacancy in vacancies:
        if not vacancy.status == STATUS_CLOSED:
            end_naive = datetime.combine(vacancy.date, vacancy.end_time)
            end_time = timezone.make_aware(end_naive, timezone.get_current_timezone())
            if end_time + timedelta(minutes=delay) < timezone.now() :
                close_vacancy(vacancy=vacancy)


@shared_task(name="vacancy.tasks.call.test_heartbeat")
def test_heartbeat():
    logger.warning("✅ test_heartbeat work")
