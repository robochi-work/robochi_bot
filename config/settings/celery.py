import os
from datetime import timedelta

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.django.production")
app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "test_heartbeat": {
        "task": "vacancy.tasks.call.test_heartbeat",
        "schedule": timedelta(seconds=30),
    },
    "before_start_call_task": {
        "task": "vacancy.tasks.call.before_start_call_task",
        "schedule": timedelta(seconds=30),
    },
    "after_first_call_check_task": {
        "task": "vacancy.tasks.call.after_first_call_check_task",
        "schedule": timedelta(seconds=30),
    },
    "start_call_check_task": {
        "task": "vacancy.tasks.call.start_call_check_task",
        "schedule": timedelta(seconds=30),
    },
    "final_call_check_task": {
        "task": "vacancy.tasks.call.final_call_check_task",
        "schedule": timedelta(seconds=30),
    },
    "close_vacancy_task": {
        "task": "vacancy.tasks.call.close_vacancy_task",
        "schedule": timedelta(seconds=30),
    },
    "close_lifecycle_timer_task": {
        "task": "vacancy.tasks.call.close_lifecycle_timer_task",
        "schedule": timedelta(seconds=30),
    },
    "worker_join_confirm_check_task": {
        "task": "vacancy.tasks.call.worker_join_confirm_check_task",
        "schedule": timedelta(seconds=30),
    },
    "resend_vacancies_to_channel_task": {
        "task": "vacancy.tasks.resend.resend_vacancies_to_channel_task",
        "schedule": timedelta(seconds=30),
    },
    "cleanup_inactive_users": {
        "task": "user.tasks.cleanup_inactive_users_task",
        "schedule": crontab(hour=3, minute=0),  # Every night at 03:00
    },
    "renewal_offer_task": {
        "task": "vacancy.tasks.call.renewal_offer_task",
        "schedule": timedelta(seconds=30),
    },
    "renewal_worker_check_task": {
        "task": "vacancy.tasks.call.renewal_worker_check_task",
        "schedule": timedelta(seconds=30),
    },
    "check_system": {
        "task": "work.tasks.check_system_task",
        "schedule": crontab(hour=4, minute=0),  # Every night at 04:00 Kyiv time
    },
    "check_logs": {
        "task": "work.tasks.check_logs_task",
        "schedule": crontab(hour=5, minute=0),  # Every night at 05:00 Kyiv time
    },
}
