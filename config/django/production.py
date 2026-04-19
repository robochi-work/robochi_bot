import os

from .base import *  # noqa: F403

DEBUG = False
HOST = os.getenv("HOST")
ALLOWED_HOSTS = [HOST, f"www.{HOST}"]
CSRF_TRUSTED_ORIGINS = [
    f"https://{HOST}",
    f"https://www.{HOST}",
]

BASE_URL: str = f"https://{HOST}"
if not HOST:
    raise ValueError("Please set the HOST environment variable")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "None"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "None"

# Security hardening
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
