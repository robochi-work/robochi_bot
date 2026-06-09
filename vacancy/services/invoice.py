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


def get_vacancy_invoice_amount(vacancy: Vacancy, price_per_worker: UAH | None = None) -> UAH:
    if price_per_worker is None:
        from work.models import PaymentConfig

        price_per_worker = PaymentConfig.get_fee()
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


def validate_invoice_data(vacancy: Vacancy) -> bool:
    """Перевірка цілісності даних перед виставленням рахунку.

    Повертає True якщо в extra["calls"]["after_start"] є >=1 працівник.
    Якщо список порожній — це АНОМАЛІЯ: шле адміну діагностичний алерт,
    логує в Sentry, повертає False.

    Ідемпотентність: алерт шлеться один раз (флаг extra["anomaly_alerted"]).
    """
    import sentry_sdk

    after_start = vacancy.extra.get("calls", {}).get(CallType.AFTER_START.value, [])
    if after_start:
        return True

    # АНОМАЛІЯ
    snapshot = vacancy.extra.get("rollcall_snapshot", []) or []
    try:
        sentry_sdk.capture_message(
            "INVOICE_ANOMALY: awaiting_payment with 0 workers",
            level="error",
            extras={
                "vacancy_id": vacancy.pk,
                "status_before": vacancy.status,
                "owner_id": vacancy.owner_id,
                "first_rollcall_passed": vacancy.first_rollcall_passed,
                "second_rollcall_passed": vacancy.second_rollcall_passed,
                "snapshot_size": len(snapshot),
                "extra_keys": list(vacancy.extra.keys()),
            },
        )
    except Exception:
        pass

    if (vacancy.extra or {}).get("anomaly_alerted"):
        return False

    try:
        from service.broadcast_service import TelegramBroadcastService
        from service.notifications_impl import TelegramNotifier
        from telegram.handlers.bot_instance import bot as _bot
        from vacancy.services.admin_format import format_user_block_with_contact

        owner_block = format_user_block_with_contact(vacancy.owner, vacancy)
        text = (
            f"🐛 BUG: спроба виставити рахунок на 0 грн\n\n"
            f"Адреса: {vacancy.address}\n\n"
            f"Замовник:\n{owner_block}\n\n"
            f"Поточний статус: {vacancy.get_status_display()}\n"
            f"1-а перекличка пройдена: {vacancy.first_rollcall_passed}\n"
            f"2-а перекличка пройдена: {vacancy.second_rollcall_passed}\n"
            f"Робочих в snapshot (1-ї переклички): {len(snapshot)}\n"
            f"Робочих в after_start (2-ї переклички): 0\n\n"
            "⚠️ Перехід в 'Очікує оплати' заблоковано.\n"
            "Розберіться чому after_start порожній."
        )
        TelegramBroadcastService(notifier=TelegramNotifier(_bot)).admin_broadcast(text=text)
    except Exception:
        sentry_sdk.capture_exception()

    vacancy.extra = dict(vacancy.extra or {})
    vacancy.extra["anomaly_alerted"] = True
    vacancy.save(update_fields=["extra"])
    return False
