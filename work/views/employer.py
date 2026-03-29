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

    likes_count = UserFeedback.objects.filter(user=request.user, rating='like').count()
    dislikes_count = UserFeedback.objects.filter(user=request.user, rating='dislike').count()
    total_count = likes_count + dislikes_count
    rating_percent = round(likes_count / total_count * 100) if total_count > 0 else 0

    enriched_reviews = []
    for review in reviews:
        vacancy_id = review.extra.get('vacancy_id') if review.extra else None
        vacancy = None
        if vacancy_id:
            vacancy = Vacancy.objects.filter(pk=vacancy_id).first()
        enriched_reviews.append({
            'review': review,
            'vacancy': vacancy,
            'rating': review.rating,
        })

    return render(request, 'work/employer_reviews.html', {
        'enriched_reviews': enriched_reviews,
        'likes_count': likes_count,
        'dislikes_count': dislikes_count,
        'total_count': total_count,
        'rating_percent': rating_percent,
        'work_profile': getattr(request.user, 'work_profile', None),
    })


@login_required
def employer_faq(request):
    """FAQ page for employers."""
    return render(request, 'work/employer_faq.html', {
        'work_profile': getattr(request.user, 'work_profile', None),
    })


@login_required
def employer_cities(request):
    """Page showing all employer's cities with channel links."""
    profile = getattr(request.user, 'work_profile', None)
    city_channels = []

    if profile:
        allowed_ids = []
        if profile.multi_city_enabled:
            allowed_ids = list(profile.allowed_cities.values_list('id', flat=True))
        if profile.city_id:
            allowed_ids.append(profile.city_id)

        if allowed_ids:
            channels = (
                Channel.objects.filter(
                    city_id__in=allowed_ids,
                    is_active=True,
                    has_bot_administrator=True,
                    invite_link__isnull=False,
                ).select_related('city')
            )
            for ch in channels:
                city_name = ch.city.safe_translation_getter('name', any_language=True) if ch.city else ch.title
                city_channels.append({
                    'city_name': city_name,
                    'channel_title': ch.title,
                    'invite_link': ch.invite_link,
                    'is_main': profile.city_id == ch.city_id,
                })
            # Main city first
            city_channels.sort(key=lambda x: (not x['is_main'], x['city_name']))

    return render(request, 'work/employer_cities.html', {
        'city_channels': city_channels,
        'work_profile': profile,
    })
