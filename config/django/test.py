"""Test settings: use SQLite to avoid needing CREATEDB privilege on production."""

from .production import *  # noqa: F401, F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "/tmp/test_robochi.sqlite3",
    }
}

# Disable password hashing to speed up tests
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Silence logging noise during tests
LOGGING = {}
