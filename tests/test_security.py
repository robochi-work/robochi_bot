"""
Regression tests for security hardening (commit 12e3678).
Covers: admin URL change, API schema protection, auth_date expiry,
        unauth redirect, Redis password, session settings.
"""

import hashlib
import hmac
import time

from django.conf import settings
from django.test import TestCase


class TestAdminURLSecurity(TestCase):
    """Admin panel must not be accessible at /admin/."""

    def test_old_admin_url_returns_404(self):
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 404)

    def test_new_admin_url_returns_redirect_to_login(self):
        response = self.client.get("/taya-panel/")
        self.assertEqual(response.status_code, 302)


class TestAPISchemaProtection(TestCase):
    """API schema and docs must require authentication."""

    def test_schema_requires_auth(self):
        response = self.client.get("/api/schema/")
        self.assertIn(response.status_code, [401, 403])

    def test_docs_requires_auth(self):
        response = self.client.get("/api/docs/")
        self.assertIn(response.status_code, [401, 403])


class TestUnauthRedirect(TestCase):
    """Unauthenticated users on root URL must be redirected to robochi.work."""

    def test_root_redirects_unauthenticated(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://robochi.work")


class TestAuthDateExpiry(TestCase):
    """WebApp auth_date must expire after 2 hours (7200s), not 24 hours."""

    def _make_init_data(self, auth_date: int) -> str:
        """Build a valid Telegram WebApp initData string."""
        import json
        from urllib.parse import urlencode

        user_data = json.dumps({"id": 123456789, "first_name": "Test"})
        params = {
            "user": user_data,
            "auth_date": str(auth_date),
        }
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
        secret_key = hmac.new(
            key=b"WebAppData",
            msg=settings.TELEGRAM_BOT_TOKEN.encode("utf-8"),
            digestmod=hashlib.sha256,
        )
        hash_value = hmac.new(
            key=secret_key.digest(),
            msg=data_check_string.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()
        params["hash"] = hash_value
        return urlencode(params)

    def test_fresh_auth_date_accepted(self):
        from telegram.utils import check_webapp_signature

        init_data = self._make_init_data(int(time.time()) - 60)
        is_valid, user_id = check_webapp_signature(init_data)
        self.assertTrue(is_valid)
        self.assertEqual(user_id, 123456789)

    def test_expired_auth_date_rejected_3h(self):
        from telegram.utils import check_webapp_signature

        init_data = self._make_init_data(int(time.time()) - 10800)
        is_valid, _ = check_webapp_signature(init_data)
        self.assertFalse(is_valid)

    def test_expired_auth_date_rejected_24h(self):
        from telegram.utils import check_webapp_signature

        init_data = self._make_init_data(int(time.time()) - 86400)
        is_valid, _ = check_webapp_signature(init_data)
        self.assertFalse(is_valid)


class TestRedisPassword(TestCase):
    """Celery broker URL must contain a password."""

    def test_celery_broker_has_password(self):
        broker = settings.CELERY_BROKER_URL
        self.assertIn("@", broker, "Redis broker URL must contain password (user@host format)")
        self.assertNotEqual(
            broker,
            "redis://localhost:6379/0",
            "Redis broker must not use passwordless connection",
        )


class TestSessionSecurity(TestCase):
    """Session and CSRF cookies must have secure settings in production."""

    def test_production_has_session_cookie_secure(self):
        """Verify production.py sets SESSION_COOKIE_SECURE = True."""
        from pathlib import Path

        prod_file = Path(__file__).resolve().parent.parent / "config" / "django" / "production.py"
        content = prod_file.read_text()
        self.assertIn("SESSION_COOKIE_SECURE = True", content)

    def test_production_has_csrf_cookie_secure(self):
        """Verify production.py sets CSRF_COOKIE_SECURE = True."""
        from pathlib import Path

        prod_file = Path(__file__).resolve().parent.parent / "config" / "django" / "production.py"
        content = prod_file.read_text()
        self.assertIn("CSRF_COOKIE_SECURE = True", content)

    def test_production_has_session_cookie_httponly(self):
        """Verify production.py sets SESSION_COOKIE_HTTPONLY = True."""
        from pathlib import Path

        prod_file = Path(__file__).resolve().parent.parent / "config" / "django" / "production.py"
        content = prod_file.read_text()
        self.assertIn("SESSION_COOKIE_HTTPONLY = True", content)
