'''
Good practice of Django settings
https://github.com/HackSoftware/Django-Styleguide
'''

from config.settings.celery import app as celery_app

__all__ = ("celery_app",)