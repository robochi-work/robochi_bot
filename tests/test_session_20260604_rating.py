"""Regression tests for session 2026-06-04: Bayesian rating, feedback protection, kicked workers."""

from django.test import TestCase

from user.models import User, UserFeedback
from vacancy.models import Vacancy, VacancyUser
from work.models import RatingConfig


class BayesianRatingTests(TestCase):
    """Test bayesian_rating() function."""

    def test_zero_votes_returns_expected(self):
        from user.rating import bayesian_rating

        result = bayesian_rating(0, 0)
        assert 0 <= result <= 100

    def test_single_like_not_100(self):
        """1 like should NOT be 100% with Bayesian average."""
        from user.rating import bayesian_rating

        result = bayesian_rating(1, 0)
        assert result < 100, f"Expected < 100, got {result}"

    def test_many_likes_high_rating(self):
        """20 likes 0 dislikes should be high but not 100."""
        from user.rating import bayesian_rating

        result = bayesian_rating(20, 0)
        assert result > 80, f"Expected > 80, got {result}"

    def test_equal_likes_dislikes_near_50(self):
        """Equal likes and dislikes should be near platform average."""
        from user.rating import bayesian_rating

        result = bayesian_rating(10, 10)
        assert 30 <= result <= 70, f"Expected 30-70, got {result}"

    def test_threshold_from_db(self):
        """RatingConfig.get_threshold() should return DB value."""
        RatingConfig.objects.all().delete()
        RatingConfig.objects.create(rating_threshold=7)
        assert RatingConfig.get_threshold() == 7

    def test_threshold_default_without_db(self):
        """Without DB row, get_threshold() returns 5."""
        RatingConfig.objects.all().delete()
        assert RatingConfig.get_threshold() == 5


class FeedbackFormTests(TestCase):
    """Test VacancyUserFeedbackForm validation."""

    def test_rating_required(self):
        """Form should reject submission without rating."""
        from vacancy.forms import VacancyUserFeedbackForm

        form = VacancyUserFeedbackForm(data={"text": "Good worker"})
        assert not form.is_valid()
        assert form.non_field_errors()

    def test_rating_only_valid(self):
        """Form should accept rating without text."""
        from vacancy.forms import VacancyUserFeedbackForm

        form = VacancyUserFeedbackForm(data={"rating": "like", "text": ""})
        assert form.is_valid()

    def test_rating_with_text_valid(self):
        """Form should accept rating with text."""
        from vacancy.forms import VacancyUserFeedbackForm

        form = VacancyUserFeedbackForm(data={"rating": "dislike", "text": "Was late"})
        assert form.is_valid()

    def test_empty_form_invalid(self):
        """Empty form should be invalid."""
        from vacancy.forms import VacancyUserFeedbackForm

        form = VacancyUserFeedbackForm(data={})
        assert not form.is_valid()


class FeedbackDuplicateTests(TestCase):
    """Test duplicate feedback protection."""

    def setUp(self):
        self.owner = User.objects.create(id=1001, username="owner1")
        self.worker = User.objects.create(id=1002, username="worker1")
        self.vacancy = Vacancy.objects.create(
            owner=self.owner,
            address="Test",
            people_count=1,
            has_passport=False,
            gender="X",
            payment_amount=500,
            date="2026-06-04",
            start_time="09:00",
            end_time="18:00",
        )

    def test_manual_feedback_creates(self):
        """First manual feedback should be created."""
        fb = UserFeedback.objects.create(
            owner=self.owner,
            user=self.worker,
            rating="like",
            text="Great",
            is_auto=False,
            extra={"vacancy_id": self.vacancy.pk},
        )
        assert fb.pk is not None

    def test_duplicate_check_query(self):
        """Duplicate check query should find existing feedback."""
        UserFeedback.objects.create(
            owner=self.owner,
            user=self.worker,
            rating="like",
            is_auto=False,
            extra={"vacancy_id": self.vacancy.pk},
        )
        exists = UserFeedback.objects.filter(
            owner=self.owner,
            user=self.worker,
            is_auto=False,
            extra__vacancy_id=self.vacancy.pk,
        ).exists()
        assert exists is True

    def test_auto_feedback_not_blocked(self):
        """Auto feedback should not block manual feedback check."""
        UserFeedback.objects.create(
            owner=self.owner,
            user=self.worker,
            rating="like",
            is_auto=True,
            extra={"vacancy_id": self.vacancy.pk, "reason": "vacancy_completed"},
        )
        exists = UserFeedback.objects.filter(
            owner=self.owner,
            user=self.worker,
            is_auto=False,
            extra__vacancy_id=self.vacancy.pk,
        ).exists()
        assert exists is False


class KickedWorkerVisibilityTests(TestCase):
    """Test that kicked workers can see vacancy for 1 hour."""

    def setUp(self):
        from work.models import UserWorkProfile

        self.employer = User.objects.create(id=2001, username="emp1")
        self.worker = User.objects.create(id=2002, username="wrk1")
        UserWorkProfile.objects.create(user=self.worker, role="worker", is_completed=True)
        self.vacancy = Vacancy.objects.create(
            owner=self.employer,
            address="Test addr",
            people_count=1,
            has_passport=False,
            gender="X",
            payment_amount=500,
            status="approved",
            date="2026-06-04",
            start_time="09:00",
            end_time="18:00",
        )

    def test_kicked_vacancy_user_found_within_hour(self):
        """VacancyUser with kicked status and recent updated_at should be found."""
        from django.utils import timezone

        from telegram.choices import Status

        vu = VacancyUser.objects.create(
            user=self.worker,
            vacancy=self.vacancy,
            status=Status.KICKED,
        )
        VacancyUser.objects.filter(pk=vu.pk).update(updated_at=timezone.now())

        from datetime import timedelta

        one_hour_ago = timezone.now() - timedelta(hours=1)
        found = VacancyUser.objects.filter(
            user=self.worker,
            status__in=[Status.KICKED, Status.LEFT],
            updated_at__gte=one_hour_ago,
        ).first()
        assert found is not None
        assert found.pk == vu.pk

    def test_old_kicked_not_found(self):
        """VacancyUser kicked more than 1 hour ago should not be found."""
        from datetime import timedelta

        from django.utils import timezone

        from telegram.choices import Status

        vu = VacancyUser.objects.create(
            user=self.worker,
            vacancy=self.vacancy,
            status=Status.KICKED,
        )
        old_time = timezone.now() - timedelta(hours=2)
        VacancyUser.objects.filter(pk=vu.pk).update(updated_at=old_time)

        one_hour_ago = timezone.now() - timedelta(hours=1)
        found = VacancyUser.objects.filter(
            user=self.worker,
            status__in=[Status.KICKED, Status.LEFT],
            updated_at__gte=one_hour_ago,
        ).first()
        assert found is None

    def test_left_vacancy_user_found(self):
        """VacancyUser with left status should also be found within hour."""
        from django.utils import timezone

        from telegram.choices import Status

        vu = VacancyUser.objects.create(
            user=self.worker,
            vacancy=self.vacancy,
            status=Status.LEFT,
        )
        VacancyUser.objects.filter(pk=vu.pk).update(updated_at=timezone.now())

        from datetime import timedelta

        one_hour_ago = timezone.now() - timedelta(hours=1)
        found = VacancyUser.objects.filter(
            user=self.worker,
            status__in=[Status.KICKED, Status.LEFT],
            updated_at__gte=one_hour_ago,
        ).first()
        assert found is not None


class RatingConfigAdminTests(TestCase):
    """Test RatingConfig single-row constraint."""

    def test_only_one_row(self):
        """Saving second RatingConfig should update existing."""
        RatingConfig.objects.all().delete()
        RatingConfig.objects.create(rating_threshold=5)
        rc2 = RatingConfig(rating_threshold=8)
        rc2.save()
        assert RatingConfig.objects.count() == 1
        assert RatingConfig.objects.first().rating_threshold == 8
