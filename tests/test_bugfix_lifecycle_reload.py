"""Regression: lifecycle.js v5 must use single reloadTimer to prevent ERR_CONNECTION_ABORTED (fix d76053f)."""

import re
from pathlib import Path


def test_lifecycle_js_has_single_reload_timer():
    """Ensure lifecycle.js uses debounced reload (reloadTimer pattern) instead of direct reload()."""
    js_path = Path("/home/webuser/robochi_bot/telegram/static/js/lifecycle.js")
    if not js_path.exists():
        js_path = Path("/home/webuser/robochi_bot/static/js/lifecycle.js")
    content = js_path.read_text()

    # Must have reloadTimer variable
    assert "reloadTimer" in content, "lifecycle.js must use reloadTimer for debounced reload"

    # reload() must appear exactly once and only inside a setTimeout block
    total_reloads = content.count("window.location.reload()")
    assert total_reloads >= 1, "lifecycle.js must call window.location.reload() at least once"

    settimeout_reloads = len(re.findall(r"setTimeout\([^;]+reload\(\)", content, re.DOTALL))
    assert settimeout_reloads >= 1, "window.location.reload() must be inside setTimeout"
    assert total_reloads == settimeout_reloads, (
        f"All {total_reloads} reload() call(s) must be inside setTimeout, "
        f"but only {settimeout_reloads} are — bare reload() would cause ERR_CONNECTION_ABORTED"
    )


def test_check_html_no_duplicate_webapp_script():
    """Ensure check.html does not duplicate telegram-web-app.js from base.html."""
    check_path = Path("/home/webuser/robochi_bot/telegram/templates/telegram/check.html")
    content = check_path.read_text()
    count = content.count("telegram-web-app.js")
    assert count <= 1, f"check.html has {count} telegram-web-app.js includes, expected 0 or 1"
