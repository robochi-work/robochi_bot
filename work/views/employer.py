from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from telegram.models import Channel
from user.models import UserFeedback
from vacancy.choices import STATUS_PENDING, STATUS_APPROVED, STATUS_ACTIVE, STATUS_CLOSED
from vacancy.models import Vacancy


@login_required
def employer_reviews(request):
    """Page showing all reviews about current employer."""
    reviews = (
        UserFeedback.objects
        .filter(user=request.user)
        .select_related('owner')
        .order_by('-created_at')
    )

    enriched_reviews = []
    for review in reviews:
        vacancy_id = review.extra.get('vacancy_id') if review.extra else None
        vacancy = None
        if vacancy_id:
            vacancy = Vacancy.objects.filter(pk=vacancy_id).first()
        enriched_reviews.append({
            'review': review,
            'vacancy': vacancy,
        })

    return render(request, 'work/employer_reviews.html', {
        'enriched_reviews': enriched_reviews,
        'work_profile': getattr(request.user, 'work_profile', None),
    })


@login_required
def employer_faq(request):
    """FAQ page for employers."""
    return render(request, 'work/employer_faq.html', {
        'work_profile': getattr(request.user, 'work_profile', None),
    })
