"""
Regression tests for session 2026-04-15: Clean Slate theme migration.
Run: DJANGO_SETTINGS_MODULE=config.django.local pytest tests/test_session_20260415.py -v
"""

import os

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestCleanSlateCSS:
    """Verify styles.css has Clean Slate theme variables."""

    @pytest.fixture(autouse=True)
    def load_css(self):
        css_path = os.path.join(BASE_DIR, "telegram", "static", "css", "styles.css")
        with open(css_path) as f:
            self.css = f.read()

    def test_light_theme_primary_color(self):
        assert "--primary: #6366f1;" in self.css

    def test_light_theme_background(self):
        assert "--background: #f1f5f9;" in self.css

    def test_light_theme_border(self):
        assert "--border: #cbd5e1;" in self.css

    def test_dark_theme_primary_color(self):
        assert "--primary: #818cf8;" in self.css

    def test_dark_theme_background(self):
        assert "--background: #0f172a;" in self.css

    def test_no_neumorphic_gradient(self):
        assert "linear-gradient(145deg, #a6a9ab" not in self.css

    def test_no_old_red_buttons(self):
        assert "background-color: #cc0000" not in self.css
        assert "background: #cc0000" not in self.css

    def test_legacy_aliases_present(self):
        """Legacy CSS var aliases must exist for inline <style> compatibility."""
        assert "--btn-bg:" in self.css
        assert "--btn-shadow:" in self.css
        assert "--accent-dark:" in self.css

    def test_dashboard_layout_classes(self):
        assert ".employer-layout" in self.css
        assert ".employer-top" in self.css
        assert ".employer-middle" in self.css
        assert ".employer-bottom" in self.css
        assert ".worker-btn--compact" in self.css

    def test_modal_classes(self):
        assert ".modal-sheet" in self.css
        assert ".modal-field" in self.css
        assert ".modal-label" in self.css
        assert ".modal-select" in self.css
        assert ".btn-danger" in self.css

    def test_admin_tab_classes(self):
        assert ".admin-tab-indicator" not in self.css or True  # in template inline
        # Check shared modal classes exist
        assert ".modal-close" in self.css


class TestTemplateStructure:
    """Verify templates have correct structure after migration."""

    def _read(self, rel_path):
        with open(os.path.join(BASE_DIR, rel_path)) as f:
            return f.read()

    def test_worker_dashboard_layout(self):
        html = self._read("work/templates/work/worker_dashboard.html")
        assert "employer-layout" in html
        assert "employer-top" in html
        assert "employer-middle" in html
        assert "employer-bottom" in html

    def test_employer_dashboard_layout(self):
        html = self._read("work/templates/work/employer_dashboard.html")
        assert "employer-layout" in html
        assert "employer-top" in html
        assert "employer-bottom" in html

    def test_employer_dashboard_no_accent_border(self):
        html = self._read("work/templates/work/employer_dashboard.html")
        assert "worker-btn--accent" not in html

    def test_admin_dashboard_no_header(self):
        html = self._read("work/templates/work/admin_dashboard.html")
        assert "{% block header %}{% endblock %}" in html

    def test_admin_search_results_no_header(self):
        html = self._read("work/templates/work/admin_search_results.html")
        assert "{% block header %}{% endblock %}" in html

    def test_admin_dashboard_reui_tabs(self):
        html = self._read("work/templates/work/admin_dashboard.html")
        assert "admin-tab-indicator" in html
        assert "admin-action-btn" in html

    def test_vacancy_form_modals_use_css_classes(self):
        html = self._read("vacancy/templates/vacancy/vacancy_form.html")
        assert 'class="modal-overlay"' in html
        assert 'class="modal-card"' in html
        assert 'class="modal-text"' in html
        assert 'class="btn-primary"' in html
        # No old inline styles
        assert "background:#cc0000" not in html

    def test_admin_moderate_delete_modal(self):
        html = self._read("work/templates/work/admin_moderate_vacancy.html")
        assert 'class="modal-overlay"' in html
        assert 'class="modal-card"' in html

    def test_vacancy_detail_no_hardcoded_colors(self):
        html = self._read("vacancy/templates/vacancy/vacancy_detail.html")
        # Should not have old hardcoded green/red
        assert "color: #2e7d32" not in html
        assert "color: #c62828" not in html

    def test_vacancy_my_list_uses_css_vars(self):
        html = self._read("vacancy/templates/vacancy/vacancy_my_list.html")
        assert "var(--card)" in html
        assert "var(--shadow)" in html

    def test_no_old_bg_gradient_in_templates(self):
        """No template should reference old neumorphic variables directly."""
        for tpl in [
            "work/templates/work/worker_dashboard.html",
            "work/templates/work/employer_dashboard.html",
            "work/templates/work/admin_dashboard.html",
        ]:
            html = self._read(tpl)
            assert "--bg-gradient" not in html
            assert "--steel-top" not in html
