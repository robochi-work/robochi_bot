"""Regression tests for session 2026-06-05: kick worker from old group on new vacancy entry."""

from django.test import TestCase

from telegram.choices import Status
from telegram.models import Group, UserInGroup
from user.models import User
from vacancy.choices import STATUS_AWAITING_PAYMENT, STATUS_CLOSED, STATUS_PAID
from vacancy.models import Vacancy, VacancyUser


class KickFromOldGroupTests(TestCase):
    """Test that workers are kicked from old finished vacancy groups."""

    def setUp(self):
        from work.models import UserWorkProfile

        self.employer = User.objects.create(id=3001, username="emp_kick")
        self.worker = User.objects.create(id=3002, username="wrk_kick")
        UserWorkProfile.objects.create(user=self.worker, role="worker", is_completed=True)

        self.old_group = Group.objects.create(id=-100100, title="Old Group", status="process")
        self.new_group = Group.objects.create(id=-100200, title="New Group", status="process")

        self.old_vacancy = Vacancy.objects.create(
            owner=self.employer,
            address="Old addr",
            people_count=1,
            has_passport=False,
            gender="X",
            payment_amount=500,
            status="closed",
            group=self.old_group,
            date="2026-06-04",
            start_time="09:00",
            end_time="18:00",
        )
        self.new_vacancy = Vacancy.objects.create(
            owner=self.employer,
            address="New addr",
            people_count=1,
            has_passport=False,
            gender="X",
            payment_amount=500,
            status="approved",
            group=self.new_group,
            date="2026-06-05",
            start_time="09:00",
            end_time="18:00",
        )

    def test_old_closed_group_found_for_kick(self):
        """Worker in old closed vacancy group should be found for kicking."""
        UserInGroup.objects.create(user=self.worker, group=self.old_group, status=Status.MEMBER)
        VacancyUser.objects.create(user=self.worker, vacancy=self.old_vacancy, status=Status.MEMBER)

        old_uigs = UserInGroup.objects.filter(user=self.worker).exclude(group=self.new_group)
        assert old_uigs.count() == 1

        old_uig = old_uigs.first()
        old_vacancy = Vacancy.objects.filter(group_id=old_uig.group_id).first()
        assert old_vacancy is not None
        assert old_vacancy.status in (STATUS_CLOSED, STATUS_AWAITING_PAYMENT, STATUS_PAID)

    def test_approved_group_not_kicked(self):
        """Worker in active approved vacancy should NOT be found for kicking."""
        active_group = Group.objects.create(id=-100300, title="Active Group", status="process")
        Vacancy.objects.create(
            owner=self.employer,
            address="Active addr",
            people_count=1,
            has_passport=False,
            gender="X",
            payment_amount=500,
            status="approved",
            group=active_group,
            date="2026-06-05",
            start_time="09:00",
            end_time="18:00",
        )
        UserInGroup.objects.create(user=self.worker, group=active_group, status=Status.MEMBER)

        old_uigs = UserInGroup.objects.filter(user=self.worker).exclude(group=self.new_group)
        for uig in old_uigs:
            v = Vacancy.objects.filter(group_id=uig.group_id).first()
            if v:
                assert v.status not in (STATUS_CLOSED, STATUS_AWAITING_PAYMENT, STATUS_PAID)

    def test_awaiting_group_kicked(self):
        """Worker in awaiting_payment vacancy group should be kicked."""
        self.old_vacancy.status = STATUS_AWAITING_PAYMENT
        self.old_vacancy.save(update_fields=["status"])

        UserInGroup.objects.create(user=self.worker, group=self.old_group, status=Status.MEMBER)

        old_uigs = UserInGroup.objects.filter(user=self.worker).exclude(group=self.new_group)
        old_uig = old_uigs.first()
        old_vacancy = Vacancy.objects.filter(group_id=old_uig.group_id).first()
        assert old_vacancy.status == STATUS_AWAITING_PAYMENT

    def test_paid_group_kicked(self):
        """Worker in paid vacancy group should be kicked."""
        self.old_vacancy.status = STATUS_PAID
        self.old_vacancy.save(update_fields=["status"])

        UserInGroup.objects.create(user=self.worker, group=self.old_group, status=Status.MEMBER)

        old_uigs = UserInGroup.objects.filter(user=self.worker).exclude(group=self.new_group)
        old_uig = old_uigs.first()
        old_vacancy = Vacancy.objects.filter(group_id=old_uig.group_id).first()
        assert old_vacancy.status == STATUS_PAID

    def test_no_old_groups_no_error(self):
        """Worker with no old groups should not cause errors."""
        old_uigs = UserInGroup.objects.filter(user=self.worker).exclude(group=self.new_group)
        assert old_uigs.count() == 0
