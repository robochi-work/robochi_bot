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
