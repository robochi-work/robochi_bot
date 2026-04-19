"""
Tests for GroupService.get_available_group (telegram/service/group.py).

The method returns the first Group with:
  - status = "available"
  - is_active = True
  - invite_link IS NOT NULL

All Telegram bot calls (create_chat_invite_link, etc.) are mocked via
the autouse mock_bot_api fixture in conftest.py.
"""

import pytest

from telegram.service.group import GroupService


@pytest.mark.django_db
def test_returns_none_when_no_groups_exist():
    result = GroupService.get_available_group()
    assert result is None


@pytest.mark.django_db
def test_returns_available_group(group_factory):
    group = group_factory(status="available", is_active=True)

    result = GroupService.get_available_group()

    assert result is not None
    assert result.id == group.id


@pytest.mark.django_db
def test_ignores_process_status_group(group_factory):
    group_factory(status="process", is_active=True)

    result = GroupService.get_available_group()

    assert result is None


@pytest.mark.django_db
def test_ignores_inactive_group(group_factory):
    group_factory(status="available", is_active=False)

    result = GroupService.get_available_group()

    assert result is None


@pytest.mark.django_db
def test_ignores_group_without_invite_link(group_factory):
    group_factory(status="available", is_active=True, invite_link=None)

    result = GroupService.get_available_group()

    assert result is None


@pytest.mark.django_db
def test_ignores_group_with_empty_invite_link(group_factory):
    """invite_link='' is not NULL — the filter uses isnull=False so empty
    string would be returned.  Verify behaviour is consistent with the query."""

    group = group_factory(status="available", is_active=True, invite_link="")

    result = GroupService.get_available_group()

    # Empty string passes isnull=False — this documents the current behaviour.
    # If this changes (e.g. blank="" check added), update this assertion.
    assert result is not None
    assert result.id == group.id


@pytest.mark.django_db
def test_returns_one_of_multiple_available_groups(group_factory):
    """
    get_available_group uses .first() with no explicit ordering and Group has
    no Meta.ordering, so the result is non-deterministic when multiple eligible
    groups exist.  The only guarantee is that the returned group is one of the
    eligible ones.
    """
    group_a = group_factory(status="available", is_active=True)
    group_b = group_factory(status="available", is_active=True)

    result = GroupService.get_available_group()

    assert result is not None
    assert result.id in {group_a.id, group_b.id}


@pytest.mark.django_db
def test_find_and_set_group_assigns_group_to_vacancy(group_factory, vacancy_factory):
    """find_and_set_group picks an available group and marks it as process."""
    group = group_factory(status="available", is_active=True)
    vacancy = vacancy_factory()

    assigned = GroupService.find_and_set_group(vacancy)

    assert assigned is not None
    assert assigned.id == group.id

    vacancy.refresh_from_db()
    assert vacancy.group_id == group.id

    group.refresh_from_db()
    assert group.status == "process"


@pytest.mark.django_db
def test_find_and_set_group_returns_none_when_no_group(vacancy_factory):
    vacancy = vacancy_factory()

    assigned = GroupService.find_and_set_group(vacancy)

    assert assigned is None
    vacancy.refresh_from_db()
    assert vacancy.group is None
