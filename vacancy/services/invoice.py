from types import SimpleNamespace
from typing import TypedDict

from django.conf import settings
from telebot.types import LabeledPrice

from service.notifications import NotificationMethod
from service.notifications_impl import TelegramNotifier
from telegram.choices import CallType
from telegram.handlers.common import CallbackStorage
from vacancy.models import Vacancy
from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter
from vacancy.services.call_markup import get_final_call_success_markup

UAH = int
COIN = int

class InvoiceData(TypedDict):
    title: str
    description: str
    invoice_payload: str
    provider_token: str
    currency: str
    prices: list[LabeledPrice]

def get_vacancy_invoice_amount(vacancy: Vacancy, price_per_worker: UAH = 100) -> UAH:
    return len(vacancy.extra.get('calls', {}).get(CallType.AFTER_START.value, [])) * price_per_worker

def get_vacancy_invoice_data(vacancy: Vacancy) -> InvoiceData:
    workers_count = len(vacancy.extra.get('calls', {}).get(CallType.AFTER_START.value, []))
    amount = get_vacancy_invoice_amount(vacancy=vacancy)
    title = CallVacancyTelegramTextFormatter(vacancy=vacancy).invoice_final_call_success()

    return InvoiceData(
        title=title,
        description=f'Вакансія №{vacancy.pk}',
        invoice_payload=CallbackStorage.invoice_payload.new(vacancy_id=vacancy.pk, amount=amount),
        provider_token=settings.PROVIDER_TOKEN,
        currency='UAH',
        prices=[
            LabeledPrice(label=f'Пошук працівників x{workers_count}', amount=amount * COIN(100))
        ],
    )

def send_vacancy_invoice(notifier: TelegramNotifier, vacancy: Vacancy) -> None:
    notifier.notify(
        recipient=SimpleNamespace(chat_id=vacancy.owner.id),
        method=NotificationMethod.INVOICE,
        vacancy=vacancy,
        **get_vacancy_invoice_data(vacancy=vacancy),
    )