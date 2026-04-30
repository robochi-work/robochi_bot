from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from user.models import UserFeedback
from vacancy.models import Vacancy
from work.models import FaqItem


@login_required
def worker_reviews(request):
    """Page showing all reviews about current worker."""
    reviews = UserFeedback.objects.filter(user=request.user).select_related("owner").order_by("-created_at")

    likes_count = UserFeedback.objects.filter(user=request.user, rating="like").count()
    dislikes_count = UserFeedback.objects.filter(user=request.user, rating="dislike").count()
    total_count = likes_count + dislikes_count
    rating_percent = round(likes_count / total_count * 100) if total_count > 0 else 0

    enriched_reviews = []
    for review in reviews:
        vacancy_id = review.extra.get("vacancy_id") if review.extra else None
        vacancy = None
        if vacancy_id:
            vacancy = Vacancy.objects.filter(pk=vacancy_id).first()
        enriched_reviews.append(
            {
                "review": review,
                "vacancy": vacancy,
                "rating": review.rating,
            }
        )

    return render(
        request,
        "work/worker_reviews.html",
        {
            "enriched_reviews": enriched_reviews,
            "likes_count": likes_count,
            "dislikes_count": dislikes_count,
            "total_count": total_count,
            "rating_percent": rating_percent,
            "work_profile": getattr(request.user, "work_profile", None),
        },
    )


@login_required
def worker_faq(request):
    """FAQ page for workers."""
    faq_items = FaqItem.objects.filter(role=FaqItem.ROLE_WORKER, is_active=True)
    return render(
        request,
        "work/worker_faq.html",
        {
            "work_profile": getattr(request.user, "work_profile", None),
            "faq_items": faq_items,
        },
    )


@login_required
def worker_my_work(request):
    """Page 'Моя робота' — worker's current vacancy detail with actions."""
    from datetime import datetime as _dt
    from datetime import timedelta

    from django.utils import timezone as _tz

    from telegram.choices import Status
    from vacancy.choices import STATUS_ACTIVE, STATUS_APPROVED
    from vacancy.models import VacancyContactPhone, VacancyUser

    user = request.user
    vacancy_user = (
        VacancyUser.objects.filter(user=user, status=Status.MEMBER)
        .select_related("vacancy", "vacancy__group", "vacancy__channel")
        .filter(vacancy__status__in=[STATUS_APPROVED, STATUS_ACTIVE])
        .first()
    )

    # Show vacancy only if worker is actually in the Telegram group
    if vacancy_user and vacancy_user.vacancy.group:
        from telegram.models import UserInGroup

        in_group = UserInGroup.objects.filter(
            user=user,
            group=vacancy_user.vacancy.group,
            status=Status.MEMBER,
        ).exists()
        if not in_group:
            vacancy_user = None

    if not vacancy_user:
        return render(
            request,
            "work/worker_my_work.html",
            {
                "vacancy": None,
                "work_profile": getattr(user, "work_profile", None),
            },
        )

    vacancy = vacancy_user.vacancy
    members = vacancy.members.select_related("user")
    members_count = members.count()

    # Contact phone visibility: show only when <= 2 hours before start_time
    show_contact_phone = False
    contact_phone = None
    _now = _tz.now()
    _start_naive = _dt.combine(vacancy.date, vacancy.start_time)
    _start_aware = _tz.make_aware(_start_naive, _tz.get_current_timezone())
    time_until_start = _start_aware - _now

    if time_until_start <= timedelta(hours=2):
        show_contact_phone = True
        cp = VacancyContactPhone.objects.filter(vacancy=vacancy, user=vacancy.owner).first()
        contact_phone = cp.phone if cp else vacancy.contact_phone

    STATUS_LABELS = {
        "pending": "Очікує модерації",
        "approved": "Активна",
        "active": "Активна",
        "stopped": "Пошук зупинено",
        "awaiting": "Очікує оплати",
        "closed": "Закрита",
        "paid": "Сплачено",
    }

    return render(
        request,
        "work/worker_my_work.html",
        {
            "vacancy": vacancy,
            "status_label": STATUS_LABELS.get(vacancy.status, vacancy.get_status_display()),
            "members_count": members_count,
            "show_contact_phone": show_contact_phone,
            "contact_phone": contact_phone,
            "work_profile": getattr(user, "work_profile", None),
        },
    )
