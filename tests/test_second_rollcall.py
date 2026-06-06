"""Tests for second rollcall (after_start) scenarios."""

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse

from telegram.choices import CallStatus, CallType, Status
from user.services import BlockService
from vacancy.choices import STATUS_SEARCH_STOPPED
from vacancy.models import VacancyUser, VacancyUserCall


@pytest.fixture
def rollcall_setup(employer_factory, worker_factory, vacancy_factory):
    owner = employer_factory()
    vacancy = vacancy_factory(
        owner=owner,
        status=STATUS_SEARCH_STOPPED,
        first_rollcall_passed=True,
        second_rollcall_passed=False,
    )
    w1 = worker_factory()
    w2 = worker_factory()
    vu1 = VacancyUser.objects.create(vacancy=vacancy, user=w1, status=Status.MEMBER)
    vu2 = VacancyUser.objects.create(vacancy=vacancy, user=w2, status=Status.MEMBER)
    return {"owner": owner, "vacancy": vacancy, "vu1": vu1, "vu2": vu2}


def _call_url(pk):
    return reverse("vacancy:call", kwargs={"pk": pk, "call_type": "after_start"})


@pytest.mark.django_db
class TestSecondRollcall:
    def test_second_rollcall_all_confirmed(self, client, rollcall_setup):
        owner = rollcall_setup["owner"]
        vacancy = rollcall_setup["vacancy"]
        vu1, vu2 = rollcall_setup["vu1"], rollcall_setup["vu2"]

        client.force_login(owner)
        # Patch send_vacancy_invoice to prevent the unrelated UNPAID block
        # that the SUCCESS observer creates for payment — not under test here.
        with patch("vacancy.services.observers.call_observer.send_vacancy_invoice"):
            response = client.post(
                _call_url(vacancy.pk),
                {"users": [vu1.pk, vu2.pk], "call_type": "after_start"},
            )

        assert response.status_code == 200
        vacancy.refresh_from_db()
        assert vacancy.second_rollcall_passed is True
        assert BlockService.is_blocked(owner) is False

    def test_second_rollcall_partial_uncheck_marks_disputed_no_block(self, client, rollcall_setup):
        """Stage 3.B: partial uncheck (Scenario Б) -> disputed state, employer NOT blocked."""
        from vacancy.services.disputed_rollcall import get_disputed, is_disputed

        owner = rollcall_setup["owner"]
        vacancy = rollcall_setup["vacancy"]
        vu1 = rollcall_setup["vu1"]

        client.force_login(owner)
        with patch("service.broadcast_service.TelegramBroadcastService") as mock_cls:
            mock_cls.return_value = MagicMock()
            response = client.post(
                _call_url(vacancy.pk),
                {"users": [vu1.pk], "call_type": "after_start"},
            )

        assert response.status_code == 200
        vacancy.refresh_from_db()
        assert vacancy.second_rollcall_passed is False
        # Employer must NOT be blocked at the dispute stage
        assert BlockService.is_blocked(owner) is False
        # Disputed state is recorded
        assert is_disputed(vacancy)
        state = get_disputed(vacancy)
        assert state["is_full_uncheck"] is False
        assert state["second_count"] == 1

    def test_second_rollcall_all_unchecked_kicks_and_blocks_employer(self, client, rollcall_setup):
        """Stage 3.B: full uncheck (Scenario В) -> employer kicked AND blocked."""

        owner = rollcall_setup["owner"]
        vacancy = rollcall_setup["vacancy"]

        client.force_login(owner)
        # TelegramBroadcastService is lazily imported inside the view function,
        # so patch the source module to intercept both the view call (which
        # incorrectly omits the notifier arg) and the observer call.
        with patch("service.broadcast_service.TelegramBroadcastService") as mock_cls:
            mock_cls.return_value = MagicMock()
            response = client.post(
                _call_url(vacancy.pk),
                {"call_type": "after_start"},
            )

        assert response.status_code == 200
        vacancy.refresh_from_db()
        assert vacancy.second_rollcall_passed is False
        assert BlockService.is_blocked(owner) is True
        assert VacancyUser.objects.filter(vacancy=vacancy, status=Status.MEMBER).count() == 2

    def test_second_rollcall_repeat_confirms_and_unblocks(self, client, rollcall_setup):
        owner = rollcall_setup["owner"]
        vacancy = rollcall_setup["vacancy"]
        vu1, vu2 = rollcall_setup["vu1"], rollcall_setup["vu2"]

        VacancyUserCall.objects.create(vacancy_user=vu1, call_type=CallType.AFTER_START, status=CallStatus.REJECT)
        VacancyUserCall.objects.create(vacancy_user=vu2, call_type=CallType.AFTER_START, status=CallStatus.REJECT)
        BlockService.auto_block_employer_rollcall_fail(user=owner)
        assert BlockService.is_blocked(owner) is True

        client.force_login(owner)
        with patch("vacancy.services.observers.call_observer.send_vacancy_invoice"):
            response = client.post(
                _call_url(vacancy.pk),
                {"users": [vu1.pk, vu2.pk], "call_type": "after_start"},
            )

        assert response.status_code == 200
        vacancy.refresh_from_db()
        assert vacancy.second_rollcall_passed is True
        assert BlockService.is_blocked(owner) is False

    def test_second_rollcall_default_checkboxes_all_checked(self, client, rollcall_setup):
        owner = rollcall_setup["owner"]
        vacancy = rollcall_setup["vacancy"]
        vu1, vu2 = rollcall_setup["vu1"], rollcall_setup["vu2"]

        client.force_login(owner)
        response = client.get(_call_url(vacancy.pk))

        assert response.status_code == 200
        form = response.context["form"]
        initial_users = form.initial.get("users", [])
        assert {u.pk for u in initial_users} == {vu1.pk, vu2.pk}

    def test_second_rollcall_repeat_visit_checkboxes_all_checked(self, client, rollcall_setup):
        owner = rollcall_setup["owner"]
        vacancy = rollcall_setup["vacancy"]
        vu1, vu2 = rollcall_setup["vu1"], rollcall_setup["vu2"]

        VacancyUserCall.objects.create(vacancy_user=vu1, call_type=CallType.AFTER_START, status=CallStatus.REJECT)
        VacancyUserCall.objects.create(vacancy_user=vu2, call_type=CallType.AFTER_START, status=CallStatus.REJECT)

        client.force_login(owner)
        response = client.get(_call_url(vacancy.pk))

        assert response.status_code == 200
        form = response.context["form"]
        initial_users = form.initial.get("users", [])
        assert {u.pk for u in initial_users} == {vu1.pk, vu2.pk}
