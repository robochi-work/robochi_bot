import os
from .base import *


DEBUG = True
ALLOWED_HOSTS = ['*']

HOST = os.getenv('HOST', 'localhost')
BASE_URL: str = f'https://{HOST}'

