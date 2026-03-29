import logging
from typing import Any

from telegram.choices import CallStatus, CallType
from user.models import UserFeedback
from vacancy.models import VacancyUserCall
from .publisher import Observer

logger = logging.getLogger(__name__)


def _already_exists(user, vacancy_pk: int, reason: str) -> bool:
    return UserFeedback.objects.filter(
        user=user,
        is_auto=True,
        extra__vacancy_id=vacancy_pk,
        extra__reason=reason,
    ).exists()


def _create_feedback(owner, user, rating: str, vacancy_pk: int, reason: str) -> None:
    if _already_exists(user, vacancy_pk, reason):
        return
    UserFeedback.objects.create(
        owner=owner,
        user=user,
        rating=rating,
        is_auto=True,
        text='',
        extra={'vacancy_id': vacancy_pk, 'reason': reason},
    )


class AutoRatingObserver(Observer):

    def update(self, event: str, data: dict[str, Any]) -> None:
        from vacancy.services.observers.events import (
            VACANCY_AFTER_START_CALL_SUCCESS,
            VACANCY_AFTER_START_CALL_FAIL,
            VACANCY_START_CALL_FAIL,
            VACANCY_CLOSE,
        )
        try:
            vacancy = data.get('vacancy')
            if not vacancy:
                return

            if event == VACANCY_AFTER_START_CALL_SUCCESS:
                self._handle_after_start_success(vacancy)
            elif event == VACANCY_AFTER_START_CALL_FAIL:
                self._handle_after_start_fail(vacancy)
            elif event == VACANCY_START_CALL_FAIL:
                self._handle_start_fail(vacancy)
            elif event == VACANCY_CLOSE:
                self._handle_close(vacancy)
        except Exception as e:
            logger.warning(f'AutoRatingObserver error on event {event}: {e}', exc_info=True)

    def _handle_after_start_success(self, vacancy) -> None:
        """All workers confirmed at final rollcall — give likes to all confirmed."""
        calls = (
            VacancyUserCall.objects
            .filter(
                vacancy_user__vacancy=vacancy,
                call_type=CallType.AFTER_START,
                status=CallStatus.CONFIRM,
            )
            .select_related('vacancy_user__user')
        )
        for call in calls:
            _create_feedback(
                owner=vacancy.owner,
                user=call.vacancy_user.user,
                rating='like',
                vacancy_pk=vacancy.pk,
                reason='vacancy_completed',
            )

    def _handle_after_start_fail(self, vacancy) -> None:
        """Final rollcall has rejects — dislike rejected, like confirmed."""
        calls = (
            VacancyUserCall.objects
            .filter(
                vacancy_user__vacancy=vacancy,
                call_type=CallType.AFTER_START,
                status__in=[CallStatus.CONFIRM, CallStatus.REJECT],
            )
            .select_related('vacancy_user__user')
        )
        for call in calls:
            worker = call.vacancy_user.user
            if call.status == CallStatus.CONFIRM:
                _create_feedback(
                    owner=vacancy.owner,
                    user=worker,
                    rating='like',
                    vacancy_pk=vacancy.pk,
                    reason='vacancy_completed',
                )
            else:
                _create_feedback(
                    owner=vacancy.owner,
                    user=worker,
                    rating='dislike',
                    vacancy_pk=vacancy.pk,
                    reason='rollcall_final_fail',
                )

    def _handle_start_fail(self, vacancy) -> None:
        """Start rollcall has rejects — dislike rejected workers only."""
        calls = (
            VacancyUserCall.objects
            .filter(
                vacancy_user__vacancy=vacancy,
                call_type=CallType.START,
                status=CallStatus.REJECT,
            )
            .select_related('vacancy_user__user')
        )
        for call in calls:
            _create_feedback(
                owner=vacancy.owner,
                user=call.vacancy_user.user,
                rating='dislike',
                vacancy_pk=vacancy.pk,
                reason='rollcall_start_fail',
            )

    def _handle_close(self, vacancy) -> None:
        """Vacancy closed — rate employer based on payment status."""
        first_member = vacancy.members.select_related('user').first()
        if not first_member:
            return

        worker = first_member.user
        if vacancy.extra.get('is_paid'):
            _create_feedback(
                owner=worker,
                user=vacancy.owner,
                rating='like',
                vacancy_pk=vacancy.pk,
                reason='vacancy_paid',
            )
        else:
            _create_feedback(
                owner=worker,
                user=vacancy.owner,
                rating='dislike',
                vacancy_pk=vacancy.pk,
                reason='vacancy_cancelled',
            )
