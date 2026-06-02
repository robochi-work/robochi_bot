"""Regression test for session 2026-05-29: STATUS_ACTIVE removal."""

import ast
import os
import subprocess

import pytest

from vacancy.choices import STATUS_APPROVED, STATUS_CLOSED, STATUS_SEARCH_STOPPED


class TestStatusActiveRemoved:
    def test_no_status_active_in_choices(self):
        from vacancy import choices

        assert not hasattr(choices, "STATUS_ACTIVE")

    def test_no_status_active_in_source_files(self):
        result = subprocess.run(
            [
                "grep",
                "-rn",
                "STATUS_ACTIVE",
                "--include=*.py",
                "--exclude-dir=venv",
                "--exclude-dir=.venv",
                "--exclude=test_session_20260529_status_active.py",
            ],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(__file__)),
        )
        assert result.stdout.strip() == ""

    def test_active_not_in_status_choices(self):
        from vacancy.choices import STATUS_CHOICES

        values = [code for code, _label in STATUS_CHOICES]
        assert "active" not in values


@pytest.mark.django_db
class TestFiltersWithoutStatusActive:
    def test_approved_vacancy_found(self, vacancy_factory):
        from vacancy.models import Vacancy

        vacancy = vacancy_factory(status=STATUS_APPROVED)
        assert Vacancy.objects.filter(status=STATUS_APPROVED, pk=vacancy.pk).exists()

    def test_approved_and_stopped_filter(self, vacancy_factory):
        from vacancy.models import Vacancy

        v1 = vacancy_factory(status=STATUS_APPROVED)
        v2 = vacancy_factory(status=STATUS_SEARCH_STOPPED)
        v3 = vacancy_factory(status=STATUS_CLOSED)
        qs = Vacancy.objects.filter(status__in=[STATUS_APPROVED, STATUS_SEARCH_STOPPED], pk__in=[v1.pk, v2.pk, v3.pk])
        pks = set(qs.values_list("pk", flat=True))
        assert v1.pk in pks and v2.pk in pks and v3.pk not in pks

    def test_active_string_not_matched(self, vacancy_factory):
        from vacancy.models import Vacancy

        v = vacancy_factory(status=STATUS_APPROVED)
        Vacancy.objects.filter(pk=v.pk).update(status="active")
        assert not Vacancy.objects.filter(status=STATUS_APPROVED, pk=v.pk).exists()


@pytest.mark.django_db
class TestAdminPanelToPayFilter:
    def test_imports_awaiting_payment(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "work", "views", "admin_panel.py")
        with open(path) as f:
            tree = ast.parse(f.read())
        names = [a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names]
        assert "STATUS_AWAITING_PAYMENT" in names
        assert "STATUS_ACTIVE" not in names
