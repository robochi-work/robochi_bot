from typing import TypedDict

import telebot
from django.conf import settings
from telebot.types import LabeledPrice

from telegram.choices import CallType
from vacancy.models import Vacancy
from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

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
    return len(vacancy.extra.get("calls", {}).get(CallType.AFTER_START.value, [])) * price_per_worker


def get_vacancy_invoice_data(vacancy: Vacancy) -> InvoiceData:
    from telegram.handlers.common import CallbackStorage

    workers_count = len(vacancy.extra.get("calls", {}).get(CallType.AFTER_START.value, []))
    amount = get_vacancy_invoice_amount(vacancy=vacancy)
    title = CallVacancyTelegramTextFormatter(vacancy=vacancy).invoice_final_call_success()

    return InvoiceData(
        title=title,
        description=f"Вакансія №{vacancy.pk}",
        invoice_payload=CallbackStorage.invoice_payload.new(vacancy_id=vacancy.pk, amount=amount),
        provider_token=settings.PROVIDER_TOKEN,
        currency="UAH",
        prices=[LabeledPrice(label=f"Пошук працівників x{workers_count}", amount=amount * COIN(100))],
    )


def send_vacancy_invoice(notifier, vacancy: Vacancy) -> None:
    import sentry_sdk
    from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

    from telegram.handlers.bot_instance import get_bot
    from user.services import BlockService

    amount = get_vacancy_invoice_amount(vacancy)
    workers_count = len(vacancy.extra.get("calls", {}).get(CallType.AFTER_START.value, []))

    if amount <= 0:
        return

    # Block employer for non-payment
    BlockService.auto_block_employer_unpaid(vacancy.owner)

    # Send message with payment WebApp button
    try:
        bot = get_bot()
        text = (
            f"За вакансією {vacancy.address} відпрацювало: {workers_count} працівників.\n"
            f"До сплати: {amount} грн.\n\n"
            f"Оплатіть рахунок щоб створювати нові вакансії."
        )
        markup = InlineKeyboardMarkup()
        payment_url = f"{settings.BASE_URL}/vacancy/{vacancy.pk}/payment/"
        markup.row(
            InlineKeyboardButton(
                "💳 Сплатити рахунок",
                web_app=telebot.types.WebAppInfo(url=payment_url),
            )
        )
        msg = bot.send_message(
            chat_id=vacancy.owner.id,
            text=text,
            reply_markup=markup,
        )
        # Save message_id for deletion after payment
        vacancy.extra["payment_message_id"] = msg.message_id
        vacancy.save(update_fields=["extra"])
    except Exception:
        sentry_sdk.capture_exception()
