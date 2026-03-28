from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q, Exists, OuterRef
from django.views.decorators.http import require_POST

from city.models import City
from user.models import User
from work.models import UserWorkProfile
from work.choices import WorkProfileRole
from vacancy.models import Vacancy
from vacancy.choices import (
    STATUS_PENDING, STATUS_APPROVED, STATUS_ACTIVE, STATUS_CLOSED,
)
from vacancy.forms import VacancyForm
from vacancy.services.observers.subscriber_setup import vacancy_publisher
from vacancy.services.observers.events import VACANCY_APPROVED as VACANCY_APPROVED_EVENT


def staff_required(view_func):
    """Decorator: login_required + is_staff check."""
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            raise Http404
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    wrapper.__doc__ = view_func.__doc__
    return wrapper


@staff_required
def admin_dashboard(request):
    """Main admin dashboard page with filter tabs."""
    cities = City.objects.all()
    return render(request, 'work/admin_dashboard.html', {
        'cities': cities,
        'roles': WorkProfileRole.choices,
        'work_profile': getattr(request.user, 'work_profile', None),
    })


@staff_required
def admin_search_users(request):
    """Search users by filters from tab."""
    qs = User.objects.select_related('work_profile', 'work_profile__city').all()

    q = request.GET.get('q', '').strip()
    if q:
        filters = Q(full_name__icontains=q) | Q(username__icontains=q) | Q(phone_number__icontains=q)
        if q.isdigit():
            filters |= Q(id=int(q))
        qs = qs.filter(filters)

    city_ids = request.GET.getlist('city')
    if city_ids:
        qs = qs.filter(work_profile__city_id__in=city_ids)

    roles = request.GET.getlist('role')
    if roles:
        qs = qs.filter(work_profile__role__in=roles)

    if request.GET.get('blocked'):
        qs = qs.filter(is_active=False)

    qs = qs.order_by('-date_joined')[:100]

    return render(request, 'work/admin_search_results.html', {
        'users': qs,
        'search_type': 'users',
        'work_profile': getattr(request.user, 'work_profile', None),
    })


@staff_required
def admin_search_vacancies(request):
    """Search employers by vacancy filters."""
    qs = User.objects.select_related('work_profile', 'work_profile__city').filter(
        work_profile__role=WorkProfileRole.EMPLOYER
    )

    city_ids = request.GET.getlist('city')
    if city_ids:
        qs = qs.filter(work_profile__city_id__in=city_ids)

    status_filters = Q()
    has_status_filter = False

    if request.GET.get('pending'):
        status_filters |= Q(vacancies__status=STATUS_PENDING)
        has_status_filter = True

    if request.GET.get('in_work'):
        status_filters |= Q(vacancies__status__in=[STATUS_APPROVED, STATUS_ACTIVE])
        has_status_filter = True

    if request.GET.get('to_pay'):
        status_filters |= Q(
            vacancies__status__in=[STATUS_ACTIVE, STATUS_CLOSED],
            vacancies__extra__sent_final_call=True,
            vacancies__extra__is_paid=False,
        )
        has_status_filter = True

    if request.GET.get('cancelled'):
        status_filters |= Q(vacancies__extra__cancel_requested=True)
        has_status_filter = True

    if has_status_filter:
        qs = qs.filter(status_filters).distinct()

    qs = qs.order_by('-date_joined')[:100]

    return render(request, 'work/admin_search_results.html', {
        'users': qs,
        'search_type': 'vacancies',
        'work_profile': getattr(request.user, 'work_profile', None),
    })


@staff_required
def admin_vacancy_card(request, user_id):
    """Vacancy card page for a specific employer."""
    target_user = get_object_or_404(User, pk=user_id)
    profile = getattr(target_user, 'work_profile', None)

    vacancies = (
        Vacancy.objects
        .filter(owner=target_user)
        .select_related('group', 'channel', 'channel__city')
        .order_by('-date', '-start_time')
    )

    cities_vacancies = {}
    for v in vacancies:
        city_name = 'Bez mista'
        if v.channel and v.channel.city:
            city_name = v.channel.city.safe_translation_getter('name', any_language=True)
        cities_vacancies.setdefault(city_name, []).append(v)

    return render(request, 'work/admin_vacancy_card.html', {
        'target_user': target_user,
        'target_profile': profile,
        'cities_vacancies': cities_vacancies,
        'work_profile': getattr(request.user, 'work_profile', None),
    })


@staff_required
def admin_moderate_vacancy(request, vacancy_id):
    """Moderation form for a single vacancy."""
    vacancy = get_object_or_404(Vacancy, pk=vacancy_id)
    work_profile = getattr(request.user, 'work_profile', None)

    if request.method == 'POST' and vacancy.status != STATUS_PENDING:
        return redirect('work:admin_vacancy_card', user_id=vacancy.owner_id)

    if request.method == 'POST':
        owner_profile = getattr(vacancy.owner, 'work_profile', None)
        form = VacancyForm(request.POST, work_profile=owner_profile)
        if form.is_valid():
            try:
                data = form.cleaned_data
                vacancy.gender = data['gender']
                vacancy.people_count = data['people_count']
                vacancy.has_passport = data['has_passport']
                vacancy.address = data['address']
                vacancy.map_link = data.get('map_link', vacancy.map_link)
                vacancy.date_choice = data['date_choice']
                vacancy.date = data.get('date', vacancy.date)
                vacancy.start_time = data['start_time']
                vacancy.end_time = data['end_time']
                vacancy.payment_amount = data['payment_amount']
                vacancy.payment_unit = data['payment_unit']
                vacancy.payment_method = data['payment_method']
                vacancy.skills = data['skills']
                vacancy.contact_phone = data.get('contact_phone', '')
                # Update channel based on selected city
                selected_city = data.get('city')
                if selected_city:
                    from telegram.models import Channel
                    try:
                        vacancy.channel = Channel.objects.get(city=selected_city)
                    except Channel.DoesNotExist:
                        form.add_error(None, f'Канал для міста {selected_city} не знайдено.')
                        return render(request, 'work/admin_moderate_vacancy.html', {
                            'form': form,
                            'vacancy': vacancy,
                            'target_user': vacancy.owner,
                            'work_profile': work_profile,
                        })
                # Assign group from pool (same logic as Django Admin save_model)
                if not vacancy.group:
                    from telegram.service.group import GroupService
                    from telegram.choices import STATUS_PROCESS
                    group = GroupService.get_available_group()
                    if group:
                        vacancy.group = group
                        group.status = STATUS_PROCESS
                        group.save(update_fields=['status'])
                    else:
                        form.add_error(None, 'Немає вільних груп для вакансії. Спробуйте пізніше.')
                        return render(request, 'work/admin_moderate_vacancy.html', {
                            'form': form,
                            'vacancy': vacancy,
                            'target_user': vacancy.owner,
                            'work_profile': work_profile,
                        })

                vacancy.status = STATUS_APPROVED
                vacancy.save()
                vacancy_publisher.notify(VACANCY_APPROVED_EVENT, {'vacancy': vacancy, 'request': request})
                return redirect('work:admin_vacancy_card', user_id=vacancy.owner_id)
            except Exception as e:
                form.add_error(None, str(e))
    else:
        initial = {
            'city': vacancy.channel.city_id if vacancy.channel else None,
            'date_choice': vacancy.date_choice,
            'gender': vacancy.gender,
            'people_count': vacancy.people_count,
            'has_passport': vacancy.has_passport,
            'address': vacancy.address,
            'map_link': vacancy.map_link,
            'start_time': vacancy.start_time,
            'end_time': vacancy.end_time,
            'payment_amount': vacancy.payment_amount,
            'payment_unit': vacancy.payment_unit,
            'payment_method': vacancy.payment_method,
            'skills': vacancy.skills,
            'contact_phone': vacancy.contact_phone,
        }
        owner_profile = getattr(vacancy.owner, 'work_profile', None)
        form = VacancyForm(initial=initial, work_profile=owner_profile)

    return render(request, 'work/admin_moderate_vacancy.html', {
        'form': form,
        'vacancy': vacancy,
        'target_user': vacancy.owner,
        'work_profile': work_profile,
    })


@staff_required
@require_POST
def admin_block_user(request, user_id):
    """Block/unblock a user."""
    target_user = get_object_or_404(User, pk=user_id)
    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=['is_active'])

    referer = request.META.get('HTTP_REFERER', '')
    if referer:
        return redirect(referer)
    return redirect('work:admin_dashboard')
