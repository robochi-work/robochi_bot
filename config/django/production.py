import os
from .base import *


DEBUG = False
HOST = os.getenv('HOST')
ALLOWED_HOSTS = [HOST, f"www.{HOST}"]
CSRF_TRUSTED_ORIGINS = [
    f'https://{HOST}',
    f'https://www.{HOST}',
]

BASE_URL: str = f'https://{HOST}'
if not HOST:
    raise ValueError('Please set the HOST environment variable')
