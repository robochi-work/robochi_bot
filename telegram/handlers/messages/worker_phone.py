import logging
import re

from telegram.choices import CallStatus, CallType
from telegram.handlers.bot_instance import bot
from user.models import User
from vacancy.models import VacancyContactPhone, VacancyUserCall

logger = logging.getLogger(__name__)

# Ukrainian phone number patterns
_PHONE_RE = re.compile(r"^(\+380\d{9}|380\d{9}|0\d{9})$")


def _normalize_phone(text: str) -> str:
    return re.sub(r"[\s\-\(\)]", "", text.strip())


def _is_valid_phone(text: str) -> bool:
    return bool(_PHONE_RE.match(_normalize_phone(text)))


@bot.message_handler(
    func=lambda m: m.chat.type == "private" and m.content_type == "text",
    content_types=["text"],
)
def handle_worker_phone(message):
    """Captures phone number from worker after they confirmed their vacancy participation."""
    user = User.objects.filter(id=message.from_user.id).first()
    if not user:
        return

    # Check if user has a pending phone request (confirmed join)
    pending_call = (
        VacancyUserCall.objects.filter(
            vacancy_user__user=user,
            call_type=CallType.WORKER_JOIN_CONFIRM.value,
            status=CallStatus.CONFIRM.value,
        )
        .select_related("vacancy_user__vacancy")
        .first()
    )

    if not pending_call:
        return  # not our message to handle

    vacancy = pending_call.vacancy_user.vacancy

    # Check if contact phone already saved for this vacancy
    if VacancyContactPhone.objects.filter(vacancy=vacancy, user=user).exists():
        return

    phone_text = message.text.strip()

    if not _is_valid_phone(phone_text):
        bot.send_message(
            chat_id=message.chat.id,
            text="Введіть коректний номер телефону!",
        )
        return

    VacancyContactPhone.objects.create(
        vacancy=vacancy,
        user=user,
        phone=_normalize_phone(phone_text),
    )

    bot.send_message(
        chat_id=message.chat.id,
        text="Дякуємо! Ваш номер збережено.",
    )
    logger.info(f"handle_worker_phone: saved contact phone for user {user.id}, vacancy {vacancy.id}")

    # Send group invite
    from vacancy.services.worker_invite import send_worker_group_invite

    send_worker_group_invite(user, vacancy)

    # Send employer contact phone if <= 2h to start
    import datetime

    from django.utils import timezone

    start_dt = datetime.datetime.combine(vacancy.date, vacancy.start_time)
    if timezone.is_naive(start_dt):
        start_dt = timezone.make_aware(start_dt)
    time_until_start = start_dt - timezone.now()
    if time_until_start <= datetime.timedelta(hours=2):
        phone = vacancy.contact_phone or getattr(vacancy.owner, "phone_number", None)
        if phone:
            bot.send_message(
                chat_id=message.chat.id,
                text=f"Контактний телефон замовника за вакансією {vacancy.address}: {phone}",
            )
