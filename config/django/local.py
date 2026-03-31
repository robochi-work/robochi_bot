import os

from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

HOST = os.getenv("HOST", "localhost")
BASE_URL: str = f"https://{HOST}"
