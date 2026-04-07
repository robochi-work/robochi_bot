"""Test settings: use SQLite to avoid needing CREATEDB privilege on production."""

from .local import *  # noqa: F401, F403

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

# Disable ManifestStaticFilesStorage — no collectstatic needed in tests
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
STORAGES = {
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
}
