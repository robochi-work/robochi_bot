"""Regression: lifecycle.js v5 must use single reloadTimer to prevent ERR_CONNECTION_ABORTED (fix d76053f)."""

import re
from pathlib import Path

# Корень проекта — 2 уровня вверх от tests/
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_lifecycle_js_has_single_reload_timer():
    """Ensure lifecycle.js uses debounced reload (reloadTimer pattern) instead of direct reload()."""
    js_path = PROJECT_ROOT / "telegram" / "static" / "js" / "lifecycle.js"
    assert js_path.exists(), f"lifecycle.js not found at {js_path}"
    content = js_path.read_text()

    # Must have reloadTimer variable
    assert "reloadTimer" in content, "lifecycle.js must use reloadTimer for debounced reload"

    # Must have setTimeout wrapping reload (supports both function() and arrow function styles)
    assert re.search(r"setTimeout\(.*?reload", content, re.DOTALL), "reload must be inside setTimeout"


def test_check_html_no_duplicate_webapp_script():
    """Ensure check.html does not duplicate telegram-web-app.js from base.html."""
    check_path = PROJECT_ROOT / "telegram" / "templates" / "telegram" / "check.html"
    assert check_path.exists(), f"check.html not found at {check_path}"
    content = check_path.read_text()
    count = content.count("telegram-web-app.js")
    assert count <= 1, f"check.html has {count} telegram-web-app.js includes, expected 0 or 1"
