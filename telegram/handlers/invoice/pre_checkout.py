from telebot.types import PreCheckoutQuery

from telegram.handlers.bot_instance import bot
from telegram.handlers.common import CallbackStorage
from telegram.models import PreCheckoutLog
from vacancy.models import Vacancy


@bot.pre_checkout_query_handler(func=lambda query: True)
def handle_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    ok = False
    try:
        data = CallbackStorage.invoice_payload.parse(pre_checkout_query.invoice_payload)
        vacancy = Vacancy.objects.get(id=data.get('vacancy_id'))

        if vacancy.extra.get('is_paid', False):
            ok = False
        else:
            ok = True

    except Exception as e:
        ok = False

    finally:
        bot.answer_pre_checkout_query(pre_checkout_query.id, ok=ok)

    if ok:
        PreCheckoutLog.objects.create(
            user_id=pre_checkout_query.from_user.id,
            pre_checkout_query_id=pre_checkout_query.id,
            invoice_payload=pre_checkout_query.invoice_payload,
            total_amount=pre_checkout_query.total_amount,
            currency=pre_checkout_query.currency,
            extra={'vacancy_id': vacancy.id},
        )