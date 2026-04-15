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
