from django.core.handlers.wsgi import WSGIRequest
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

from telegram.choices import Status
from telegram.models import Channel
from user.models import UserFeedback
from vacancy.choices import STATUS_APPROVED, STATUS_ACTIVE
from vacancy.models import VacancyUser
from work.blocks.registry import block_registry


@login_required
def index(request: WSGIRequest):
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
            VacancyUser.objects
            .filter(user=user, status=Status.MEMBER)
            .select_related("vacancy", "vacancy__group")
            .filter(vacancy__status__in=[STATUS_APPROVED, STATUS_ACTIVE])
            .first()
        )
        if vacancy_user:
            current_vacancy = vacancy_user.vacancy

        # Reviews count
        reviews_count = UserFeedback.objects.filter(user=user).count()

        context = {
            "work_profile": profile,
            "channel": channel,
            "current_vacancy": current_vacancy,
            "reviews_count": reviews_count,
        }
        return render(request, "work/worker_dashboard.html", context)

    # Employer — standard block-based dashboard
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
