import re
import logging

from telegram.choices import CallType, CallStatus
from telegram.handlers.bot_instance import bot
from user.models import User
from vacancy.models import VacancyUserCall

logger = logging.getLogger(__name__)

# Ukrainian phone number patterns
_PHONE_RE = re.compile(
    r'^(\+380\d{9}|380\d{9}|0\d{9})$'
)


def _normalize_phone(text: str) -> str:
    return re.sub(r'[\s\-\(\)]', '', text.strip())


def _is_valid_phone(text: str) -> bool:
    return bool(_PHONE_RE.match(_normalize_phone(text)))


@bot.message_handler(
    func=lambda m: m.chat.type == 'private' and m.content_type == 'text',
    content_types=['text'],
)
def handle_worker_phone(message):
    """Captures phone number from worker after they confirmed their vacancy participation."""
    user = User.objects.filter(id=message.from_user.id).first()
    if not user:
        return

    # Check if user has a pending phone request
    pending_call = VacancyUserCall.objects.filter(
        vacancy_user__user=user,
        call_type=CallType.WORKER_JOIN_CONFIRM.value,
        status=CallStatus.CONFIRM.value,
    ).first()

    if not pending_call:
        return  # not our message to handle

    if user.phone_number:
        # Phone already saved — nothing to do
        return

    phone_text = message.text.strip()

    if not _is_valid_phone(phone_text):
        bot.send_message(
            chat_id=message.chat.id,
            text=(
                'Невірний формат номера. '
                'Введіть номер у форматі +380XXXXXXXXX або 0XXXXXXXXX.'
            ),
        )
        return

    user.phone_number = _normalize_phone(phone_text)
    user.save(update_fields=['phone_number'])

    bot.send_message(
        chat_id=message.chat.id,
        text='Дякуємо! Ваш номер збережено.',
    )
    logger.info(f'handle_worker_phone: saved phone for user {user.id}')
