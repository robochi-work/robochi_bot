"""Regression: lifecycle.js must guard against multiple rapid reloads (ERR_CONNECTION_ABORTED fix)."""

import re
from pathlib import Path

# Корень проекта — 2 уровня вверх от tests/
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_lifecycle_js_has_single_reload_timer():
    """lifecycle.js v7+: uses recovering flag + pingAndReload to debounce reloads."""
    js_path = PROJECT_ROOT / "telegram" / "static" / "js" / "lifecycle.js"
    assert js_path.exists(), f"lifecycle.js not found at {js_path}"
    content = js_path.read_text()

    # v7+: recovering flag prevents concurrent reload attempts
    assert "recovering" in content, "lifecycle.js must have a guard to prevent multiple reloads"

    # v7: reload is deferred via pingAndReload (fetch-based), which is itself called from setTimeout
    assert "pingAndReload" in content, "lifecycle.js must use pingAndReload for ping-before-reload flow"
    assert re.search(r"setTimeout\(.*?pingAndReload", content, re.DOTALL), "pingAndReload must be called via setTimeout"


def test_check_html_no_duplicate_webapp_script():
    """Ensure check.html does not duplicate telegram-web-app.js from base.html."""
    check_path = PROJECT_ROOT / "telegram" / "templates" / "telegram" / "check.html"
    assert check_path.exists(), f"check.html not found at {check_path}"
    content = check_path.read_text()
    count = content.count("telegram-web-app.js")
    assert count <= 1, f"check.html has {count} telegram-web-app.js includes, expected 0 or 1"
