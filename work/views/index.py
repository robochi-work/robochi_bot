from django.core.handlers.wsgi import WSGIRequest
from django.shortcuts import redirect, render

from telegram.choices import Status
from telegram.models import Channel
from user.models import UserFeedback
from user.services import BlockService
from vacancy.choices import STATUS_ACTIVE, STATUS_APPROVED
from vacancy.models import Vacancy, VacancyUser
from work.blocks.registry import block_registry
from work.choices import WorkProfileRole


def index(request: WSGIRequest):
    if not request.user.is_authenticated:
        return redirect("https://robochi.work")
    user = request.user

    # If phone not confirmed, redirect to phone-required page
    if not user.phone_number:
        return redirect("work:phone_required")

    # Administrator — separate dashboard, skip wizard check
    if user.is_staff:
        return redirect("work:admin_dashboard")

    profile = getattr(user, "work_profile", None)

    # Worker — dedicated dashboard
    if profile and profile.role == "worker":
        # City channel link
        channel = None
        if profile.city:
            channel = Channel.objects.filter(
                city=profile.city,
                is_active=True,
                has_bot_administrator=True,
                invite_link__isnull=False,
            ).first()

        # Current active vacancy (worker is member of)
        current_vacancy = None
        vacancy_user = (
            VacancyUser.objects.filter(user=user, status=Status.MEMBER)
            .select_related("vacancy", "vacancy__group")
            .filter(vacancy__status__in=[STATUS_APPROVED, STATUS_ACTIVE])
            .first()
        )
        if vacancy_user and vacancy_user.vacancy.group:
            from telegram.models import UserInGroup

            in_group = UserInGroup.objects.filter(
                user=user,
                group=vacancy_user.vacancy.group,
                status=Status.MEMBER,
            ).exists()
            if in_group:
                current_vacancy = vacancy_user.vacancy

        # Reviews count
        reviews_count = UserFeedback.objects.filter(user=user).count()

        is_blocked = BlockService.is_blocked(user)
        context = {
            "work_profile": profile,
            "channel": channel,
            "current_vacancy": current_vacancy,
            "reviews_count": reviews_count,
            "is_blocked": is_blocked,
            "active_block": BlockService.get_active_block(user) if is_blocked else None,
        }
        return render(request, "work/worker_dashboard.html", context)

    # Employer — dedicated dashboard
    if profile and profile.role == WorkProfileRole.EMPLOYER:
        # First visit: no vacancies yet → redirect to create
        if Vacancy.objects.filter(owner=user).count() == 0:
            return redirect("vacancy:create")

        # Active vacancies count
        active_vacancies_count = Vacancy.objects.filter(
            owner=user,
            status__in=[STATUS_APPROVED, STATUS_ACTIVE],
        ).count()

        # Reviews count
        reviews_count = UserFeedback.objects.filter(user=user).count()

        # City channel link (single city)
        channel = None
        if profile.city:
            channel = Channel.objects.filter(
                city=profile.city,
                is_active=True,
                has_bot_administrator=True,
                invite_link__isnull=False,
            ).first()

        # Multi-city: collect all city channels
        city_channels = None
        if profile.multi_city_enabled:
            allowed_ids = list(profile.allowed_cities.values_list("id", flat=True))
            if profile.city_id:
                allowed_ids.append(profile.city_id)
            city_channels = list(
                Channel.objects.filter(
                    city_id__in=allowed_ids,
                    is_active=True,
                    has_bot_administrator=True,
                    invite_link__isnull=False,
                ).select_related("city")
            )

        is_blocked = BlockService.is_blocked(user)
        context = {
            "work_profile": profile,
            "active_vacancies_count": active_vacancies_count,
            "reviews_count": reviews_count,
            "channel": channel,
            "city_channels": city_channels,
            "is_blocked": is_blocked,
            "active_block": BlockService.get_active_block(user) if is_blocked else None,
        }
        return render(request, "work/employer_dashboard.html", context)

    # Fallback — block-based dashboard
    blocks = []
    for block in block_registry.get_visible_blocks(request):
        ctx = block.get_context(request)
        ctx["block"] = block
        blocks.append(ctx)

    context = {
        "rendered_blocks": blocks,
        "work_profile": profile,
    }
    return render(request, "work/index.html", context=context)
