from collections import defaultdict
from typing import Iterable

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse, HttpRequest, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.translation import gettext as _
from telegram.choices import CallStatus, CallType, Status
from user.models import User, UserFeedback
from vacancy.choices import STATUS_PENDING, STATUS_APPROVED, STATUS_ACTIVE, STATUS_CLOSED
from vacancy.forms import VacancyForm, VacancyCallForm, CallTypes, VacancyUserFeedbackForm
from vacancy.models import Vacancy, VacancyUserCall, VacancyUser
from vacancy.services.call import create_vacancy_call
from vacancy.services.observers import events
from vacancy.services.observers.events import VACANCY_START_CALL_FAIL, VACANCY_AFTER_START_CALL_FAIL, \
    VACANCY_AFTER_START_CALL_SUCCESS, VACANCY_REFIND, VACANCY_NEW_FEEDBACK
from vacancy.services.observers.subscriber_setup import vacancy_publisher
from vacancy.tasks.call import before_start_call, after_first_call_check


def vacancy_create(request):
    from user.services import BlockService
    if BlockService.is_blocked(request.user):
        return redirect('index')

    work_profile = getattr(request.user, 'work_profile', None)
    if request.method == 'POST':
        vacancy_form = VacancyForm(request.POST, work_profile=work_profile)
        if vacancy_form.is_valid():
            # Защита от двойного создания: проверяем дубль за последние 60 секунд
            from django.utils import timezone
            from datetime import timedelta
            recent = Vacancy.objects.filter(
                owner=request.user,
                status=STATUS_PENDING,
                address=vacancy_form.cleaned_data.get('address', ''),
                date=vacancy_form.cleaned_data.get('date') or vacancy_form.cleaned_data.get('date_choice'),
                start_time=vacancy_form.cleaned_data.get('start_time'),
            ).first()
            if recent:
                return redirect('index')
            new_vacancy = vacancy_form.save(owner=request.user, status=STATUS_PENDING)
            vacancy_publisher.notify(events.VACANCY_CREATED, data={'vacancy': new_vacancy, 'request': request})
            return redirect('index')

    else:
        # Pre-fill form from last vacancy as template (except date_choice)
        initial = {}
        last_vacancy = (
            Vacancy.objects
            .filter(owner=request.user)
            .order_by('-id')
            .first()
        )
        if last_vacancy:
            initial = {
                'gender': last_vacancy.gender,
                'people_count': last_vacancy.people_count,
                'has_passport': last_vacancy.has_passport,
                'address': last_vacancy.address,
                'map_link': last_vacancy.map_link,
                'start_time': last_vacancy.start_time,
                'end_time': last_vacancy.end_time,
                'payment_amount': last_vacancy.payment_amount,
                'payment_unit': last_vacancy.payment_unit,
                'payment_method': last_vacancy.payment_method,
                'skills': last_vacancy.skills,
                'contact_phone': last_vacancy.contact_phone,
            }
        vacancy_form = VacancyForm(initial=initial, work_profile=work_profile)


    # First visit = employer has never created any vacancy
    is_first_visit = not Vacancy.objects.filter(owner=request.user).exists()
    return render(request, 'vacancy/vacancy_form_page.html', {
        'form': vacancy_form,
        'is_first_visit': is_first_visit,
        'work_profile': work_profile,
    })


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


def vacancy_user_feedback(request: WSGIRequest, pk: int, user_id: int) -> HttpResponse:
    vacancy = get_object_or_404(Vacancy, pk=pk)
    target_user = get_object_or_404(User, pk=user_id)

    if request.method == 'POST':
        form = VacancyUserFeedbackForm(request.POST)
        if form.is_valid():
            rating = form.cleaned_data.get('rating') or 'none'
            text = form.cleaned_data.get('text', '')
            feedback = UserFeedback.objects.create(
                owner=request.user,
                user=target_user,
                text=text,
                rating=rating,
                extra={'vacancy_id': vacancy.pk},
            )
            vacancy_publisher.notify(VACANCY_NEW_FEEDBACK, data={'vacancy': vacancy, 'feedback': feedback})
            messages.success(request, _('Feedback has been sent.'))
            return redirect('index')
    else:
        form = VacancyUserFeedbackForm()

    return render(request, 'vacancy/vacancy_feedback.html', context={
        'form': form,
        'vacancy': vacancy,
        'target_user': target_user,
    })


def vacancy_user_list(request: WSGIRequest, pk: int) -> HttpResponse:
    vacancy = get_object_or_404(Vacancy, pk=pk)

    all_users = [vm.user for vm in vacancy.members.select_related('user')]
    if vacancy.owner_id != request.user.id:
        all_users.append(vacancy.owner)
    users = [u for u in all_users if u.id != request.user.id]

    work_profile = getattr(request.user, 'work_profile', None)
    user_role = work_profile.role if work_profile else None
    contact_phone = vacancy.contact_phone or getattr(vacancy.owner, 'phone_number', None)

    return render(request, 'vacancy/vacancy_user_list.html', context={
        'vacancy': vacancy,
        'users': users,
        'user_role': user_role,
        'contact_phone': contact_phone,
    })


def vacancy_user_reviews(request: WSGIRequest, pk: int, user_id: int) -> HttpResponse:
    vacancy = get_object_or_404(Vacancy, pk=pk)
    target_user = get_object_or_404(User, pk=user_id)

    feedbacks = (
        UserFeedback.objects
        .filter(user=target_user)
        .select_related('owner')
        .order_by('-created_at')
    )
    likes = feedbacks.filter(rating='like').count()
    dislikes = feedbacks.filter(rating='dislike').count()

    return render(request, 'vacancy/vacancy_user_reviews.html', context={
        'vacancy': vacancy,
        'target_user': target_user,
        'feedbacks': feedbacks,
        'likes': likes,
        'dislikes': dislikes,
    })

def vacancy_test_task(request):
    return HttpResponse(status=200)


@login_required
def vacancy_my_list(request):
    """List of all employer's vacancies with statuses."""
    statuses = [STATUS_PENDING, STATUS_APPROVED, STATUS_ACTIVE]
    vacancies = (
        Vacancy.objects
        .filter(owner=request.user, status__in=statuses)
        .select_related('group', 'channel')
        .order_by('-date', '-start_time')
    )

    STATUS_LABELS = {
        STATUS_PENDING: 'Очікує модерації',
        STATUS_APPROVED: 'Активна (пошук)',
        STATUS_ACTIVE: 'Йде зміна',
        'closed': 'Завершена',
    }

    vacancy_list = []
    for v in vacancies:
        vacancy_list.append({
            'vacancy': v,
            'status_label': STATUS_LABELS.get(v.status, v.get_status_display()),
            'members_count': v.members.count(),
        })

    return render(request, 'vacancy/vacancy_my_list.html', {
        'vacancy_list': vacancy_list,
        'work_profile': getattr(request.user, 'work_profile', None),
    })


@login_required
def vacancy_detail(request, pk):
    """Detail page for a single vacancy with management buttons."""
    vacancy = get_object_or_404(Vacancy, pk=pk, owner=request.user)

    STATUS_LABELS = {
        STATUS_PENDING: 'Очікує модерації',
        STATUS_APPROVED: 'Активна (пошук)',
        STATUS_ACTIVE: 'Йде зміна',
        'closed': 'Завершена',
    }

    members = vacancy.members.select_related('user')

    return render(request, 'vacancy/vacancy_detail.html', {
        'vacancy': vacancy,
        'status_label': STATUS_LABELS.get(vacancy.status, vacancy.get_status_display()),
        'members': members,
        'members_count': members.count(),
        'work_profile': getattr(request.user, 'work_profile', None),
    })


@login_required
def vacancy_stop_search(request, pk):
    """Stop search: remove button from channel, notify admins."""
    vacancy = get_object_or_404(Vacancy, pk=pk, owner=request.user)

    if vacancy.status in [STATUS_APPROVED, STATUS_ACTIVE]:
        from telegram.handlers.bot_instance import bot
        from telegram.models import ChannelMessage
        from service.notifications import NotificationMethod
        from service.telegram_strategy_factory import TelegramStrategyFactory
        from vacancy.services.vacancy_formatter import VacancyTelegramTextFormatter

        # Update channel message to "Пошук завершено" (no button)
        if vacancy.channel:
            text = VacancyTelegramTextFormatter(vacancy).for_channel(status='full')
            channel_message = ChannelMessage.objects.filter(
                channel_id=vacancy.channel.id,
                extra__vacancy_id=vacancy.id,
            ).order_by('-id').first()
            if channel_message:
                strategy = TelegramStrategyFactory.get_strategy(NotificationMethod.TEXT)
                try:
                    strategy.update(bot, vacancy.channel.id, text=text, message_id=channel_message.message_id)
                except Exception as e:
                    import logging
                    logging.warning(f'Failed to update channel message: {e}')

        # Set status to closed
        vacancy.status = STATUS_CLOSED
        vacancy.save(update_fields=['status'])

    return redirect('vacancy:detail', pk=pk)


@login_required
def vacancy_members(request, pk):
    """Page showing all users who joined the vacancy group."""
    vacancy = get_object_or_404(Vacancy, pk=pk, owner=request.user)

    all_users = (
        VacancyUser.objects
        .filter(vacancy=vacancy)
        .select_related('user')
        .order_by('-created_at')
    )

    members_list = []
    for vu in all_users:
        feedbacks = UserFeedback.objects.filter(user=vu.user).count()
        members_list.append({
            'vacancy_user': vu,
            'user': vu.user,
            'status': vu.get_status_display(),
            'is_member': vu.status == 'member',
            'feedbacks_count': feedbacks,
        })

    return render(request, 'vacancy/vacancy_members.html', {
        'vacancy': vacancy,
        'members_list': members_list,
        'work_profile': getattr(request.user, 'work_profile', None),
    })


@login_required
def vacancy_send_contact(request: WSGIRequest, pk: int) -> JsonResponse:
    """Send vacancy owner's contact phone to the worker via bot."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Method not allowed'}, status=405)

    work_profile = getattr(request.user, 'work_profile', None)
    if not work_profile or work_profile.role != 'worker':
        return JsonResponse({'ok': False, 'error': 'Only workers can request contacts'}, status=403)

    vacancy = get_object_or_404(Vacancy, pk=pk)
    phone = vacancy.contact_phone or getattr(vacancy.owner, 'phone_number', None)
    if not phone:
        return JsonResponse({'ok': False, 'error': 'Телефон замовника не вказано'})

    try:
        from telegram.handlers.bot_instance import bot
        text = f'Контактний телефон замовника за вакансією {vacancy.address}: {phone}'
        bot.send_message(chat_id=request.user.telegram_id, text=text)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)})

    return JsonResponse({'ok': True})


@login_required
def vacancy_kick_member(request, pk, user_id):
    """Kick a worker from vacancy group."""
    if request.method != 'POST':
        return redirect('vacancy:members', pk=pk)

    vacancy = get_object_or_404(Vacancy, pk=pk, owner=request.user)

    from telegram.service.group import GroupService
    if vacancy.group:
        GroupService.kick_user(chat_id=vacancy.group.id, user_id=user_id)

    return redirect('vacancy:members', pk=pk)
