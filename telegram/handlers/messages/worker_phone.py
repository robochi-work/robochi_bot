import logging
import re

from telegram.choices import CallStatus, CallType
from telegram.handlers.bot_instance import bot
from user.models import User
from vacancy.models import VacancyContactPhone, VacancyUserCall

logger = logging.getLogger(__name__)

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
    """Captures NEW phone number from worker who chose 'Змінити' or has no contact_phone yet."""
    user = User.objects.filter(id=message.from_user.id).first()
    if not user:
        return

    # Find the CONFIRM call where contact phone is NOT yet saved (worker chose "Change" or first time)
    pending_calls = (
        VacancyUserCall.objects.filter(
            vacancy_user__user=user,
            call_type=CallType.WORKER_JOIN_CONFIRM.value,
            status=CallStatus.CONFIRM.value,
        )
        .select_related("vacancy_user__vacancy")
        .order_by("-created_at")
    )

    vacancy = None
    for pc in pending_calls:
        if not VacancyContactPhone.objects.filter(vacancy=pc.vacancy_user.vacancy, user=user).exists():
            vacancy = pc.vacancy_user.vacancy
            break

    if not vacancy:
        return

    phone_text = message.text.strip()

    if not _is_valid_phone(phone_text):
        bot.send_message(
            chat_id=message.chat.id,
            text="Введіть коректний номер телефону!",
        )
        return

    normalized = _normalize_phone(phone_text)

    # Save to VacancyContactPhone (for this vacancy)
    VacancyContactPhone.objects.create(
        vacancy=vacancy,
        user=user,
        phone=normalized,
    )

    # Persist to User.contact_phone (for future vacancies)
    if user.contact_phone != normalized:
        user.contact_phone = normalized
        user.save(update_fields=["contact_phone"])

    bot.send_message(
        chat_id=message.chat.id,
        text="Дякуємо! Ваш номер збережено.",
    )
    logger.info(f"handle_worker_phone: saved contact phone for user {user.id}, vacancy {vacancy.id}")

    # Send group invite
    from vacancy.services.worker_invite import send_worker_group_invite

    send_worker_group_invite(user, vacancy)
