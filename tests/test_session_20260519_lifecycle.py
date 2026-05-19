"""
Regression tests for session cookie and lifecycle fixes (2026-05-19).
Covers:
  - Production session settings (SameSite=Lax, AGE=2weeks, SAVE_EVERY_REQUEST)
  - lifecycle.js v7 (ping-before-reload, overlay)
  - Dead code removal from telegram.js (alpine:init block)
"""

from pathlib import Path

from django.test import TestCase

BASE_DIR = Path(__file__).resolve().parent.parent


class TestProductionSessionSettings(TestCase):
    """Production settings must have safe session/CSRF cookie values."""

    def _read_production_settings(self):
        path = BASE_DIR / "config" / "django" / "production.py"
        return path.read_text()

    def test_session_cookie_samesite_is_lax(self):
        text = self._read_production_settings()
        self.assertIn('SESSION_COOKIE_SAMESITE = "Lax"', text)
        self.assertNotIn('SESSION_COOKIE_SAMESITE = "None"', text)

    def test_csrf_cookie_samesite_is_lax(self):
        text = self._read_production_settings()
        self.assertIn('CSRF_COOKIE_SAMESITE = "Lax"', text)
        self.assertNotIn('CSRF_COOKIE_SAMESITE = "None"', text)

    def test_session_cookie_age_two_weeks(self):
        text = self._read_production_settings()
        self.assertIn("SESSION_COOKIE_AGE = 1209600", text)

    def test_session_save_every_request_enabled(self):
        text = self._read_production_settings()
        self.assertIn("SESSION_SAVE_EVERY_REQUEST = True", text)

    def test_csrf_cookie_httponly_false(self):
        """CSRF cookie must be readable by JS (Django default)."""
        text = self._read_production_settings()
        self.assertIn("CSRF_COOKIE_HTTPONLY = False", text)


class TestLifecycleJS(TestCase):
    """lifecycle.js v7 must ping server before reloading."""

    def _read_lifecycle(self):
        path = BASE_DIR / "telegram" / "static" / "js" / "lifecycle.js"
        return path.read_text()

    def test_ping_before_reload_exists(self):
        text = self._read_lifecycle()
        self.assertIn("fetch(", text, "Must ping server with fetch before reload")

    def test_overlay_exists(self):
        text = self._read_lifecycle()
        self.assertIn("lifecycle-overlay", text, "Must show loading overlay on resume")

    def test_broadcast_channel_guard(self):
        text = self._read_lifecycle()
        self.assertIn("BroadcastChannel", text, "Single-instance guard must be present")

    def test_multiple_resume_events(self):
        text = self._read_lifecycle()
        self.assertIn("visibilitychange", text)
        self.assertIn("focus", text)
        self.assertIn("pageshow", text)
        self.assertIn("activated", text)


class TestTelegramJSCleanup(TestCase):
    """Dead alpine:init code must be removed from telegram.js."""

    def _read_telegram_js(self):
        path = BASE_DIR / "telegram" / "static" / "js" / "telegram.js"
        return path.read_text()

    def test_no_alpine_init(self):
        text = self._read_telegram_js()
        self.assertNotIn("alpine:init", text, "Dead alpine:init listener must be removed")

    def test_no_getCookie(self):
        text = self._read_telegram_js()
        self.assertNotIn("getCookie", text, "Undefined getCookie function call must be removed")
