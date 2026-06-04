def bayesian_rating(likes: int, dislikes: int) -> int:
    """
    Bayesian average rating as integer percent (0-100).

    Formula: (C * m + likes) / (C + total) * 100
    C = rating_threshold from RatingConfig (admin-editable, default 5)
    m = platform-wide average like ratio (computed dynamically)
    """
    from user.models import UserFeedback
    from work.models import RatingConfig

    C = RatingConfig.get_threshold()

    # Platform-wide average
    from django.db.models import Q

    agg = UserFeedback.objects.filter(Q(rating="like") | Q(rating="dislike")).values_list("rating", flat=True)
    total_likes = sum(1 for r in agg if r == "like")
    total_all = len(agg)
    m = total_likes / total_all if total_all > 0 else 0.5

    total = likes + dislikes
    if total == 0 and C == 0:
        return 0
    score = (C * m + likes) / (C + total)
    return round(score * 100)
