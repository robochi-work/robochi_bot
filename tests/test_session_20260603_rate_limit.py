"""
Regression tests for worker voluntary exit rate limiting.
Feature: Worker can press "Я ГОТОВИЙ ПРАЦЮВАТИ" max 2 times per hour.
Only VOLUNTARY exits count (status="left", not "kicked").
On 3rd attempt: block + auto-dislike.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from telegram.choices import Status
from user.models import User, UserFeedback, WorkerVoluntaryExit
from vacancy.choices import GENDER_ANY, STATUS_APPROVED
from vacancy.models import Vacancy, VacancyUser


@pytest.fixture
def worker(db):
    from work.models import UserWorkProfile

    user = User.objects.create(id=999001, username="test_worker")
    UserWorkProfile.objects.create(user=user, role="worker", is_completed=True)
    return user


@pytest.fixture
def employer(db):
    from work.models import UserWorkProfile

    user = User.objects.create(id=999002, username="test_employer")
    UserWorkProfile.objects.create(user=user, role="employer", is_completed=True)
    return user


@pytest.fixture
def vacancy_factory(db, employer):
    from city.models import City
    from telegram.models import Channel, Group

    city = City.objects.create(id=99, order=99)
    channel = Channel.objects.create(id=-1009990001, city=city, has_bot_administrator=True)

    def _create(group_id, **kwargs):
        group = Group.objects.create(id=group_id, title=f"Group {group_id}", invite_link="https://t.me/+test")
        defaults = {
            "owner": employer,
            "status": STATUS_APPROVED,
            "gender": GENDER_ANY,
            "people_count": 5,
            "address": "Test",
            "has_passport": False,
            "payment_amount": 500,
            "payment_unit": "per_hour",
            "payment_method": "cash",
            "date": timezone.now().date(),
            "start_time": (timezone.now() + timedelta(hours=2)).time(),
            "end_time": (timezone.now() + timedelta(hours=8)).time(),
            "channel": channel,
            "group": group,
        }
        defaults.update(kwargs)
        return Vacancy.objects.create(**defaults)

    return _create


# ---- Model tests ----


class TestWorkerVoluntaryExitModel:
    def test_create_voluntary_exit(self, worker, vacancy_factory):
        vacancy = vacancy_factory(-1009990010)
        exit_record = WorkerVoluntaryExit.objects.create(user=worker, vacancy=vacancy)
        assert exit_record.pk is not None
        assert exit_record.user == worker
        assert exit_record.vacancy == vacancy

    def test_count_exits_in_last_hour(self, worker, vacancy_factory):
        v1 = vacancy_factory(-1009990011)
        v2 = vacancy_factory(-1009990012)

        # 2 exits in last hour
        WorkerVoluntaryExit.objects.create(user=worker, vacancy=v1)
        WorkerVoluntaryExit.objects.create(user=worker, vacancy=v2)

        one_hour_ago = timezone.now() - timedelta(hours=1)
        count = WorkerVoluntaryExit.objects.filter(user=worker, created_at__gte=one_hour_ago).count()
        assert count == 2

    def test_old_exits_not_counted(self, worker, vacancy_factory):
        v1 = vacancy_factory(-1009990013)

        # Exit from 2 hours ago
        exit_record = WorkerVoluntaryExit.objects.create(user=worker, vacancy=v1)
        WorkerVoluntaryExit.objects.filter(pk=exit_record.pk).update(created_at=timezone.now() - timedelta(hours=2))

        one_hour_ago = timezone.now() - timedelta(hours=1)
        count = WorkerVoluntaryExit.objects.filter(user=worker, created_at__gte=one_hour_ago).count()
        assert count == 0


# ---- Rate limit in apply_vacancy tests ----


class TestApplyVacancyRateLimit:
    @patch("telegram.handlers.callback.apply_vacancy.bot")
    def test_no_block_with_zero_exits(self, mock_bot, worker, vacancy_factory):
        """Worker with 0 exits can press the button."""
        vacancy = vacancy_factory(-1009990020)

        call = MagicMock()
        call.id = "test_call_1"
        call.data = f"apply:{vacancy.id}"
        call.from_user.id = worker.id
        call.from_user.username = worker.username

        from telegram.handlers.callback.apply_vacancy import handle_apply_vacancy

        handle_apply_vacancy(call)

        # Should NOT get rate limit alert
        for c in mock_bot.answer_callback_query.call_args_list:
            if c.kwargs.get("text") or (c.args and len(c.args) > 1):
                text = c.kwargs.get("text", c.args[1] if len(c.args) > 1 else "")
                assert "Багато спроб" not in text

    @patch("telegram.handlers.callback.apply_vacancy.bot")
    def test_no_block_with_one_exit(self, mock_bot, worker, vacancy_factory):
        """Worker with 1 exit can still press the button."""
        v1 = vacancy_factory(-1009990021)
        vacancy = vacancy_factory(-1009990022)

        WorkerVoluntaryExit.objects.create(user=worker, vacancy=v1)

        call = MagicMock()
        call.id = "test_call_2"
        call.data = f"apply:{vacancy.id}"
        call.from_user.id = worker.id
        call.from_user.username = worker.username

        from telegram.handlers.callback.apply_vacancy import handle_apply_vacancy

        handle_apply_vacancy(call)

        for c in mock_bot.answer_callback_query.call_args_list:
            if c.kwargs.get("text") or (c.args and len(c.args) > 1):
                text = c.kwargs.get("text", c.args[1] if len(c.args) > 1 else "")
                assert "Багато спроб" not in text

    @patch("telegram.handlers.callback.apply_vacancy.bot")
    def test_block_after_two_exits(self, mock_bot, worker, vacancy_factory):
        """Worker with 2 exits in last hour gets blocked on 3rd attempt."""
        v1 = vacancy_factory(-1009990023)
        v2 = vacancy_factory(-1009990024)
        v3 = vacancy_factory(-1009990025)

        WorkerVoluntaryExit.objects.create(user=worker, vacancy=v1)
        WorkerVoluntaryExit.objects.create(user=worker, vacancy=v2)

        call = MagicMock()
        call.id = "test_call_3"
        call.data = f"apply:{v3.id}"
        call.from_user.id = worker.id
        call.from_user.username = worker.username

        from telegram.handlers.callback.apply_vacancy import handle_apply_vacancy

        handle_apply_vacancy(call)

        mock_bot.answer_callback_query.assert_called_once_with(
            call.id,
            show_alert=True,
            text="Багато спроб обрати вакансію! Спробуйте через годину!",
        )

    @patch("telegram.handlers.callback.apply_vacancy.bot")
    def test_auto_dislike_created_on_block(self, mock_bot, worker, vacancy_factory):
        """Auto-dislike is created when worker is rate-limited."""
        v1 = vacancy_factory(-1009990026)
        v2 = vacancy_factory(-1009990027)
        v3 = vacancy_factory(-1009990028)

        WorkerVoluntaryExit.objects.create(user=worker, vacancy=v1)
        WorkerVoluntaryExit.objects.create(user=worker, vacancy=v2)

        assert UserFeedback.objects.filter(user=worker, extra__reason="excessive_exits").count() == 0

        call = MagicMock()
        call.id = "test_call_4"
        call.data = f"apply:{v3.id}"
        call.from_user.id = worker.id
        call.from_user.username = worker.username

        from telegram.handlers.callback.apply_vacancy import handle_apply_vacancy

        handle_apply_vacancy(call)

        fb = UserFeedback.objects.filter(user=worker, extra__reason="excessive_exits")
        assert fb.count() == 1
        assert fb.first().rating == "dislike"
        assert fb.first().is_auto is True

    @patch("telegram.handlers.callback.apply_vacancy.bot")
    def test_no_duplicate_dislike_on_repeated_attempts(self, mock_bot, worker, vacancy_factory):
        """Multiple blocked attempts within the same hour create only 1 dislike."""
        v1 = vacancy_factory(-1009990029)
        v2 = vacancy_factory(-1009990030)
        v3 = vacancy_factory(-1009990031)
        v4 = vacancy_factory(-1009990032)

        WorkerVoluntaryExit.objects.create(user=worker, vacancy=v1)
        WorkerVoluntaryExit.objects.create(user=worker, vacancy=v2)

        from telegram.handlers.callback.apply_vacancy import handle_apply_vacancy

        # 3rd attempt
        call = MagicMock()
        call.id = "test_call_5a"
        call.data = f"apply:{v3.id}"
        call.from_user.id = worker.id
        call.from_user.username = worker.username
        handle_apply_vacancy(call)

        # 4th attempt
        call2 = MagicMock()
        call2.id = "test_call_5b"
        call2.data = f"apply:{v4.id}"
        call2.from_user.id = worker.id
        call2.from_user.username = worker.username
        handle_apply_vacancy(call2)

        # Still only 1 dislike
        assert UserFeedback.objects.filter(user=worker, extra__reason="excessive_exits").count() == 1

    @patch("telegram.handlers.callback.apply_vacancy.bot")
    def test_old_exits_dont_block(self, mock_bot, worker, vacancy_factory):
        """Exits older than 1 hour don't count toward the limit."""
        v1 = vacancy_factory(-1009990033)
        v2 = vacancy_factory(-1009990034)
        v3 = vacancy_factory(-1009990035)

        e1 = WorkerVoluntaryExit.objects.create(user=worker, vacancy=v1)
        e2 = WorkerVoluntaryExit.objects.create(user=worker, vacancy=v2)

        # Move both exits to 2 hours ago
        WorkerVoluntaryExit.objects.filter(pk__in=[e1.pk, e2.pk]).update(created_at=timezone.now() - timedelta(hours=2))

        call = MagicMock()
        call.id = "test_call_6"
        call.data = f"apply:{v3.id}"
        call.from_user.id = worker.id
        call.from_user.username = worker.username

        from telegram.handlers.callback.apply_vacancy import handle_apply_vacancy

        handle_apply_vacancy(call)

        for c in mock_bot.answer_callback_query.call_args_list:
            if c.kwargs.get("text") or (c.args and len(c.args) > 1):
                text = c.kwargs.get("text", c.args[1] if len(c.args) > 1 else "")
                assert "Багато спроб" not in text


# ---- Group handler voluntary exit detection ----


class TestGroupHandlerVoluntaryExit:
    def test_voluntary_exit_logged_on_left_status(self, worker, vacancy_factory):
        """When Telegram sends status='left', a WorkerVoluntaryExit is created."""
        vacancy = vacancy_factory(-1009990040)
        from telegram.models import Group, UserInGroup

        group = Group.objects.get(id=-1009990040)
        UserInGroup.objects.create(user=worker, group=group, status=Status.MEMBER)
        VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.MEMBER)

        event = MagicMock()
        event.new_chat_member.user.id = worker.id
        event.new_chat_member.user.is_bot = False
        event.new_chat_member.user.username = worker.username
        event.new_chat_member.status = "left"
        event.old_chat_member.status = "member"
        event.chat.id = -1009990040
        event.chat.type = "supergroup"
        event.chat.title = "Test Group"

        with (
            patch("telegram.handlers.member.user.group.bot"),
            patch("telegram.service.group.GroupService.kick_user"),
            patch("vacancy.services.observers.subscriber_setup.vacancy_publisher"),
        ):
            from telegram.handlers.member.user.group import handle_user_status_change

            handle_user_status_change(event)

        assert WorkerVoluntaryExit.objects.filter(user=worker, vacancy=vacancy).count() == 1

    def test_kicked_not_logged_as_voluntary(self, worker, employer, vacancy_factory):
        """When Telegram sends status='kicked', NO WorkerVoluntaryExit is created."""
        vacancy = vacancy_factory(-1009990041)
        from telegram.models import Group, UserInGroup

        group = Group.objects.get(id=-1009990041)
        UserInGroup.objects.create(user=worker, group=group, status=Status.MEMBER)
        VacancyUser.objects.create(user=worker, vacancy=vacancy, status=Status.MEMBER)

        event = MagicMock()
        event.new_chat_member.user.id = worker.id
        event.new_chat_member.user.is_bot = False
        event.new_chat_member.user.username = worker.username
        event.new_chat_member.status = "kicked"
        event.old_chat_member.status = "member"
        event.chat.id = -1009990041
        event.chat.type = "supergroup"
        event.chat.title = "Test Group"

        with (
            patch("telegram.handlers.member.user.group.bot"),
            patch("telegram.service.group.GroupService.kick_user"),
            patch("vacancy.services.observers.subscriber_setup.vacancy_publisher"),
        ):
            from telegram.handlers.member.user.group import handle_user_status_change

            handle_user_status_change(event)

        assert WorkerVoluntaryExit.objects.filter(user=worker, vacancy=vacancy).count() == 0
