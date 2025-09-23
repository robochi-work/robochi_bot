from django.utils import timezone
from telebot.types import PreCheckoutQuery, Message

from telegram.handlers.bot_instance import bot
from telegram.handlers.common import CallbackStorage
from telegram.models import PreCheckoutLog, PaymentStatus, Payment
from vacancy.models import Vacancy


@bot.message_handler(content_types=['successful_payment'])
def handle_successful_payment(message: Message):
    sp = message.successful_payment
    data = CallbackStorage.invoice_payload.parse(sp.invoice_payload)
    extra = {}
    vacancy = None
    try:
        vacancy = Vacancy.objects.get(id=data.get('vacancy_id'))
        vacancy.extra['is_paid'] = True
        vacancy.save(update_fields=['extra'])

        extra.update({'vacancy_id': vacancy.id})
    finally:

        Payment.objects.create(
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            currency=sp.currency,
            invoice_payload=sp.invoice_payload,
            total_amount=sp.total_amount,
            telegram_payment_charge_id=sp.telegram_payment_charge_id,
            provider_payment_charge_id=sp.provider_payment_charge_id,
            status=PaymentStatus.SUCCESSFUL,
            date=timezone.now(),
            vacancy=vacancy,
            extra=extra,
        )

