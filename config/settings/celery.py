import os
from datetime import timedelta

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.django.production')
app = Celery('config')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'test_heartbeat': {
        'task': 'vacancy.tasks.call.test_heartbeat',
        'schedule': timedelta(seconds=30),
    },
    'before_start_call_task': {
        'task': 'vacancy.tasks.call.before_start_call_task',
        'schedule': timedelta(seconds=30),
    },
    'after_first_call_check_task': {
        'task': 'vacancy.tasks.call.after_first_call_check_task',
        'schedule': timedelta(seconds=30),
    },
    'start_call_check_task': {
        'task': 'vacancy.tasks.call.start_call_check_task',
        'schedule': timedelta(seconds=30),
    },
    'final_call_check_task': {
        'task': 'vacancy.tasks.call.final_call_check_task',
        'schedule': timedelta(seconds=30),
    },
    'close_vacancy_task': {
        'task': 'vacancy.tasks.call.close_vacancy_task',
        'schedule': timedelta(seconds=30),
    },
    'resend_vacancies_to_channel_task': {
        'task': 'vacancy.tasks.resend.resend_vacancies_to_channel_task',
        'schedule': timedelta(seconds=30),
    },
}
