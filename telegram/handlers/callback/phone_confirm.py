import json
import logging

from telebot.types import CallbackQuery

from telegram.handlers.bot_instance import bot
from user.models import User
from vacancy.models import Vacancy, VacancyContactPhone

logger = logging.getLogger(__name__)


@bot.callback_query_handler(func=lambda c: c.data and '"t": "phone_confirm"' in c.data)
def handle_phone_confirm(callback: CallbackQuery) -> None:
    """Handle worker's contact phone confirm/change buttons."""
    try:
        data = json.loads(callback.data)
    except (json.JSONDecodeError, TypeError):
        return

    if data.get("t") != "phone_confirm":
        return

    user = User.objects.filter(id=callback.from_user.id).first()
    if not user:
        return

    vacancy = Vacancy.objects.filter(id=data.get("v")).first()
    if not vacancy:
        return

    bot.delete_message(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
    )

    if data.get("s") == "confirm":
        # Save current contact_phone to VacancyContactPhone
        VacancyContactPhone.objects.get_or_create(
            vacancy=vacancy,
            user=user,
            defaults={"phone": user.contact_phone},
        )
        bot.send_message(
            chat_id=callback.message.chat.id,
            text="Дякуємо! Ваш номер підтверджено.",
        )
        logger.info(f"phone_confirm: user {user.id} confirmed phone for vacancy {vacancy.id}")

        # Send group invite
        from vacancy.services.worker_invite import send_worker_group_invite

        send_worker_group_invite(user, vacancy)

        # Send employer contact if <= 2h to start
        _send_employer_contact_if_needed(callback.message.chat.id, vacancy)

    elif data.get("s") == "change":
        # Ask to enter new phone
        bot.send_message(
            chat_id=callback.message.chat.id,
            text="Напишіть новий контактний номер телефону",
        )
        logger.info(f"phone_confirm: user {user.id} chose to change phone for vacancy {vacancy.id}")

    bot.answer_callback_query(callback.id)


def _send_employer_contact_if_needed(chat_id: int, vacancy: Vacancy) -> None:
    import datetime

    from django.utils import timezone

    start_dt = datetime.datetime.combine(vacancy.date, vacancy.start_time)
    if timezone.is_naive(start_dt):
        start_dt = timezone.make_aware(start_dt)
    time_until_start = start_dt - timezone.now()
    if time_until_start <= datetime.timedelta(hours=2):
        try:
            cp = VacancyContactPhone.objects.filter(vacancy=vacancy, user=vacancy.owner).first()
            phone = cp.phone if cp else None
        except Exception:
            phone = None
        if phone:
            bot.send_message(
                chat_id=chat_id,
                text=f"Контактний телефон замовника за вакансією {vacancy.address}: {phone}",
            )
