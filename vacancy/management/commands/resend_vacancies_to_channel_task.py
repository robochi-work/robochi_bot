from django.core.management.base import BaseCommand
from vacancy.tasks.resend import resend_vacancies_to_channel_task


class Command(BaseCommand):
    help = "Resend vacancies to channel task"

    def handle(self, *args, **options):

        resend_vacancies_to_channel_task()
