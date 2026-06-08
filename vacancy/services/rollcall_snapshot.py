"""Snapshot helper for the 1st-rollcall workers list.

Used by the 2nd rollcall, vacancy detail page and worker dashboard
so that workers who left/were kicked between rollcalls are still shown.
"""

from __future__ import annotations

from collections.abc import Iterable

from vacancy.models import Vacancy, VacancyUser

SNAPSHOT_KEY = "rollcall_snapshot"


def save_first_rollcall_snapshot(vacancy: Vacancy, user_ids: Iterable[int]) -> None:
    """Save confirmed user_ids from the 1st rollcall into vacancy.extra."""
    vacancy.extra[SNAPSHOT_KEY] = list({int(uid) for uid in user_ids})
    vacancy.save(update_fields=["extra"])


def get_snapshot_user_ids(vacancy: Vacancy) -> list[int]:
    """Return snapshot user_ids or empty list."""
    return list(vacancy.extra.get(SNAPSHOT_KEY) or [])


def get_snapshot_vacancy_users(vacancy: Vacancy):
    """Return QuerySet[VacancyUser] for users in snapshot.

    Falls back to vacancy.members if snapshot is empty (backward compat
    for vacancies created before this feature).
    """
    user_ids = get_snapshot_user_ids(vacancy)
    if not user_ids:
        return vacancy.members
    return VacancyUser.objects.filter(vacancy=vacancy, user_id__in=user_ids).select_related("user")


def is_user_in_snapshot(vacancy: Vacancy, user) -> bool:
    return user.id in get_snapshot_user_ids(vacancy)
