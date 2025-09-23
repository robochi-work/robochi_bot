from collections import defaultdict
from typing import Iterable

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse, HttpRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.translation import gettext as _
from telegram.choices import CallStatus, CallType, Status
from user.models import User, UserFeedback
from vacancy.choices import STATUS_PENDING
from vacancy.forms import VacancyForm, VacancyCallForm, CallTypes, VacancyUserFeedbackForm
from vacancy.models import Vacancy, VacancyUserCall, VacancyUser
from vacancy.services.call import create_vacancy_call
from vacancy.services.observers import events
from vacancy.services.observers.events import VACANCY_START_CALL_FAIL, VACANCY_AFTER_START_CALL_FAIL, \
    VACANCY_AFTER_START_CALL_SUCCESS, VACANCY_REFIND, VACANCY_NEW_FEEDBACK
from vacancy.services.observers.subscriber_setup import vacancy_publisher
from vacancy.tasks.call import before_start_call, after_first_call_check


def vacancy_create(request):
    if request.method == 'POST':
        vacancy_form = VacancyForm(request.POST)
        if vacancy_form.is_valid():
            new_vacancy = vacancy_form.save(owner=request.user, status=STATUS_PENDING)
            vacancy_publisher.notify(events.VACANCY_CREATED, data={'vacancy': new_vacancy, 'request': request})
            return redirect('index')

    else:
        vacancy_form = VacancyForm()

    return render(request, 'vacancy/vacancy_form_page.html', {'form': vacancy_form})


def vacancy_check_call(request: WSGIRequest, form: VacancyCallForm, vacancy: Vacancy, call_type: CallType):

    if form.is_valid():
        users_queryset = form.fields['users'].queryset

        create_vacancy_call(
            vacancy=vacancy,
            call_type=call_type,
            status=CallStatus.CREATED,
        )
        selected_users = list(form.cleaned_data.get('users', []))
        vacancy_users_call = VacancyUserCall.objects.filter(vacancy_user__in=users_queryset, call_type=call_type)
        confirmed_count: int = (
            vacancy_users_call
            .filter(vacancy_user__in=selected_users)
            .update(
                status=CallStatus.CONFIRM,
            )
        )

        if call_type == CallType.START:
            vacancy.extra['start_pre_call'] = 'continue'
            (
                VacancyUserCall.objects.filter(vacancy_user__in=users_queryset, call_type=CallType.BEFORE_START)
                .filter(vacancy_user__in=selected_users)
                .update(
                    status=CallStatus.CONFIRM,
                )
            )

        rejected_users: int = (
            vacancy_users_call
            .exclude(vacancy_user__in=selected_users)
            .update(
                status=CallStatus.REJECT,
            )
        )
        extra_calls = vacancy.extra.get('calls', defaultdict(dict))
        extra_calls[call_type] = [i.user.id for i in selected_users]
        vacancy.extra.update({'calls': extra_calls})
        vacancy.save(update_fields=['extra'])

        if rejected_users > 0:
            if call_type == CallType.START:
                vacancy_publisher.notify(VACANCY_START_CALL_FAIL, data={'vacancy': vacancy})
            elif call_type == CallType.AFTER_START:
                vacancy_publisher.notify(VACANCY_AFTER_START_CALL_FAIL, data={'vacancy': vacancy})
        else:
            if call_type == CallType.AFTER_START:
                vacancy_publisher.notify(VACANCY_AFTER_START_CALL_SUCCESS, data={'vacancy': vacancy})



        return render(request, 'vacancy/call_confirm.html', context={'form': form})
    return None

def vacancy_pre_call_check(request: WSGIRequest, pk: int, call_type: CallType):
    vacancy: Vacancy = get_object_or_404(Vacancy, pk=pk)
    users_queryset = vacancy.members
    if call_type == CallType.START:
        vacancy.extra['pre_call_start'] = True
        vacancy.save(update_fields=['extra'])

        if vacancy.extra.get('start_pre_call', 'need') in ['need']:
            can_request_find_users_again = users_queryset.count() < vacancy.people_count

            if can_request_find_users_again:
                return render(request, 'vacancy/pre_call.html', context={'pk': pk, 'call_type': call_type, 'members_count': users_queryset.count()})

    return redirect('vacancy:call', pk=pk, call_type=call_type)

def vacancy_start_refind(request: WSGIRequest, pk: int):
    vacancy = get_object_or_404(Vacancy, pk=pk)
    vacancy.extra['start_pre_call'] = 'need'
    vacancy.save(update_fields=['extra'])

    vacancy_publisher.notify(VACANCY_REFIND, data={'vacancy': vacancy})
    return render(request, 'vacancy/refind_start.html')

def vacancy_call(request: WSGIRequest, pk: int, call_type: CallType) -> HttpResponse:
    vacancy = get_object_or_404(Vacancy, pk=pk)
    users_queryset = vacancy.members
    form = VacancyCallForm(request.POST, queryset=users_queryset, call_type=call_type)

    if request.method == 'POST':
        call_answer = vacancy_check_call(request=request, form=form, vacancy=vacancy, call_type=call_type)
        if call_answer:
            return call_answer
    else:
        initial_calls = VacancyUserCall.objects.filter(
            vacancy_user__in=users_queryset,
            status=CallStatus.CONFIRM,
            call_type=call_type,
        )
        form = VacancyCallForm(
            queryset=users_queryset,
            call_type=call_type,
            initial={'users': [user_call.vacancy_user for user_call in initial_calls]},
        )

    return render(request, 'vacancy/call.html', context={'form': form, 'call_type': call_type})


def vacancy_user_feedback(request: WSGIRequest, pk: int) -> HttpResponse:
    vacancy = get_object_or_404(Vacancy, pk=pk)

    users = [vm.user for vm in vacancy.members] + [vacancy.owner]
    filtered_users = [u for u in users if u.id != request.user.id]

    if request.method == 'POST':
        form = VacancyUserFeedbackForm(request.POST, vacancy=vacancy, users=filtered_users)
        if form.is_valid():
            target_user_id = form.cleaned_data['users']
            target_user = User.objects.get(pk=target_user_id)

            feedback = UserFeedback.objects.create(
                owner=request.user,
                user=target_user,
                text=form.cleaned_data['text'],
                extra={'vacancy_id': vacancy.pk},
            )
            vacancy_publisher.notify(VACANCY_NEW_FEEDBACK, data={'vacancy': vacancy, 'feedback': feedback})
            messages.success(request, _('Feedback has been sent.'))
            return redirect('index')
    else:
        form = VacancyUserFeedbackForm(vacancy=vacancy, users=filtered_users)

    return render(request, 'vacancy/vacancy_feedback.html', context={'form': form, 'vacancy': vacancy})

def vacancy_test_task(request):
    return HttpResponse(status=200)
