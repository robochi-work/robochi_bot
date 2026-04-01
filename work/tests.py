from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Regression tests for check_system management command
# ---------------------------------------------------------------------------
# These tests guard against AttributeError bugs where status constants were
# incorrectly referenced as class attributes (e.g. Group.STATUS_AVAILABLE)
# instead of being imported from their choices modules.
# Bug fixed: work/management/commands/check_system.py
# ---------------------------------------------------------------------------


def _mock_qs():
    """Return a mock queryset that returns no results."""
    qs = MagicMock()
    qs.filter.return_value = qs
    qs.exists.return_value = False
    return qs


def test_check_groups_no_attribute_error():
    """_check_groups() must not raise AttributeError for Group.STATUS_AVAILABLE."""
    from work.management.commands.check_system import _check_groups

    with patch("telegram.models.Group.objects") as mock_objects:
        mock_objects.filter.return_value = _mock_qs()
        result = _check_groups()

    assert result.ok is True


def test_check_approved_vacancies_no_attribute_error():
    """_check_approved_vacancies() must not raise AttributeError for Vacancy.STATUS_APPROVED."""
    from work.management.commands.check_system import _check_approved_vacancies

    with patch("vacancy.models.Vacancy.objects") as mock_objects:
        mock_objects.filter.return_value = _mock_qs()
        result = _check_approved_vacancies()

    assert result.ok is True


def test_check_channels_no_attribute_error():
    """_check_channels() must not raise any unexpected exception."""
    from work.management.commands.check_system import _check_channels

    with patch("telegram.models.Channel.objects") as mock_objects:
        mock_objects.filter.return_value = _mock_qs()
        result = _check_channels()

    assert result.ok is True


def test_check_vacancy_user_orphans_no_attribute_error():
    """_check_vacancy_user_orphans() must not raise any unexpected exception."""
    from work.management.commands.check_system import _check_vacancy_user_orphans

    with patch("vacancy.models.VacancyUser.objects") as mock_objects:
        mock_objects.filter.return_value = _mock_qs()
        result = _check_vacancy_user_orphans()

    assert result.ok is True


def test_run_checks_returns_all_results():
    """run_checks() must return a list with one result per check function (currently 7)."""
    from work.management.commands.check_system import CheckResult, run_checks

    ok = CheckResult(ok=True, label="mock")
    with (
        patch("work.management.commands.check_system._check_channels", return_value=ok),
        patch("work.management.commands.check_system._check_groups", return_value=ok),
        patch("work.management.commands.check_system._check_vacancy_user_orphans", return_value=ok),
        patch("work.management.commands.check_system._check_approved_vacancies", return_value=ok),
        patch("work.management.commands.check_system._check_observer_subscriptions", return_value=ok),
        patch("work.management.commands.check_system._check_celery_beat", return_value=ok),
        patch("work.management.commands.check_system._check_webhook_url", return_value=ok),
    ):
        results = run_checks()

    assert len(results) == 7
    for r in results:
        assert hasattr(r, "ok")
        assert hasattr(r, "label")
