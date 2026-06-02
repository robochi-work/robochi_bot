"""
Regression test: no decorative emoji icons in WebApp HTML templates.
✕ (U+2715, modal close button) is explicitly allowed and must not be flagged.
"""

import re
from pathlib import Path

import pytest

# U+2715 (✕) is a functional close-button character, not a decorative emoji.
ALLOWED = frozenset("✕")  # ✕ only

EMOJI_PATTERN = re.compile(
    "["
    "\U0001f300-\U0001f9ff"  # Misc symbols, emoticons, transport, supplemental
    "\U0001fa00-\U0001faff"  # Symbols and pictographs extended-A
    "☀-⛿"  # Misc symbols (☀ ⚙ ⛿ …)
    "✀-➿"  # Dingbats (✂ ✉ ✕ ✓ …) — filtered post-match
    "⭐"  # ⭐ star
    "‼⁉"  # ‼ ⁉
    "™ℹ"  # ™ ℹ
    "⏩-⏺"  # ⏩ ⏰ ⏺ …
    "▶◀"  # ▶ ◀
    "⤴⤵"  # ⤴ ⤵
    "✅"  # ✅
    "✓-✔"  # ✓ ✔
    "️"  # variation selector-16
    "]+",
    re.UNICODE,
)

TEMPLATES = [
    "work/templates/work/worker_dashboard.html",
    "work/templates/work/employer_dashboard.html",
    "work/templates/work/admin_dashboard.html",
    "work/templates/work/employer_cities.html",
    "work/templates/work/admin_search_results.html",
    "work/templates/work/employer_reviews.html",
    "work/templates/work/worker_my_work.html",
    "vacancy/templates/vacancy/vacancy_detail.html",
    "vacancy/templates/vacancy/vacancy_my_list.html",
    "vacancy/templates/vacancy/vacancy_payment.html",
    "vacancy/templates/vacancy/vacancy_members.html",
    "vacancy/templates/vacancy/vacancy_feedback.html",
    "vacancy/templates/vacancy/vacancy_user_reviews.html",
    "vacancy/templates/vacancy/pre_call.html",
    "vacancy/templates/vacancy/vacancy_form.html",
    "work/templates/work/includes/dashboard_bottom.html",
]

BASE_DIR = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("rel_path", TEMPLATES)
def test_no_emoji_in_template(rel_path):
    path = BASE_DIR / rel_path
    assert path.exists(), f"Template file not found: {rel_path}"

    content = path.read_text(encoding="utf-8")
    found = [ch for ch in EMOJI_PATTERN.findall(content) if ch not in ALLOWED]

    assert not found, f"Found emoji(s) in {rel_path}: " + ", ".join(f"{ch!r} (U+{ord(ch):04X})" for ch in found)
