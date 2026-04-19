import logging

import sentry_sdk
from celery import shared_task
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from telegram.handlers.bot_instance import bot

logger = logging.getLogger(__name__)

_MAX_RETRIES = 10
_RETRY_INTERVAL_SECONDS = 60


@shared_task(bind=True, max_retries=_MAX_RETRIES, default_retry_delay=_RETRY_INTERVAL_SECONDS)
def send_employer_group_invite_task(self, vacancy_id: int):
    """
    Надсилає заказчику повідомлення з посиланням на групу вакансії.
    Повторює кожну хвилину до 10 разів, поки заказчик не зайде в групу.
    """
    from telegram.choices import Status
    from vacancy.choices import STATUS_ACTIVE, STATUS_APPROVED
    from vacancy.models import Vacancy, VacancyUser

    try:
        vacancy = Vacancy.objects.select_related("group", "owner").get(id=vacancy_id)
    except Vacancy.DoesNotExist:
        logger.warning("employer_invite_vacancy_not_found", extra={"vacancy_id": vacancy_id})
        return

    # Вакансія вже не активна — зупиняємо
    if vacancy.status not in [STATUS_APPROVED, STATUS_ACTIVE]:
        logger.info("employer_invite_vacancy_closed", extra={"vacancy_id": vacancy_id})
        _delete_invite_message(vacancy)
        return

    # Заказчик вже в групі — зупиняємо
    owner_in_group = VacancyUser.objects.filter(
        user=vacancy.owner,
        vacancy=vacancy,
        status__in=[Status.OWNER, Status.MEMBER],
    ).exists()

    if owner_in_group:
        logger.info("employer_already_in_group", extra={"vacancy_id": vacancy_id})
        _delete_invite_message(vacancy)
        return

    if not vacancy.group or not vacancy.group.invite_link:
        logger.warning("employer_invite_no_group", extra={"vacancy_id": vacancy_id})
        return

    # Видалити попереднє повідомлення
    _delete_invite_message(vacancy)

    # Надіслати нове
    try:
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton(
                text="Перейти в групу вакансії",
                url=vacancy.group.invite_link,
            )
        )

        sent = bot.send_message(
            chat_id=vacancy.owner.id,
            text="Перейдіть у групу Вашої вакансії для спілкування з робітниками.",
            reply_markup=markup,
        )

        vacancy.extra = vacancy.extra or {}
        vacancy.extra["employer_invite_msg_id"] = sent.message_id
        vacancy.save(update_fields=["extra"])

        logger.info(
            "employer_invite_sent",
            extra={"vacancy_id": vacancy_id, "retry": self.request.retries},
        )
    except Exception:
        sentry_sdk.capture_exception()

    # Якщо є ще спроби — повторити через 1 хвилину
    if self.request.retries < _MAX_RETRIES:
        raise self.retry()
    else:
        # 10 спроб вичерпано — заказчик не зайшов у групу
        logger.warning(
            "employer_invite_max_retries",
            extra={"vacancy_id": vacancy_id},
        )

        # 1. Видалити повідомлення-запрошення
        _delete_invite_message(vacancy)

        # 2. Видалити всі сервісні повідомлення цієї вакансії з бота заказчика
        _delete_all_vacancy_messages(vacancy)

        # 3. Надіслати повідомлення в групу і кікнути рабочих
        if vacancy.group:
            try:
                bot.send_message(
                    chat_id=vacancy.group.id,
                    text="⚠️ Увага!\nДана вакансія відмінена!\nВийдіть з даної групи щоб знаходити інші вакансії!",
                )
            except Exception:
                sentry_sdk.capture_exception()

        # 4. Закрити вакансію через publisher (стандартний алгоритм)
        from vacancy.services.observers import events
        from vacancy.services.observers.subscriber_setup import vacancy_publisher

        vacancy.extra = vacancy.extra or {}
        vacancy.extra["cancel_requested"] = True
        vacancy.extra["closed_reason"] = "employer_no_group"
        vacancy.save(update_fields=["extra"])

        vacancy_publisher.notify(events.VACANCY_CLOSE, data={"vacancy": vacancy})

        # 5. Заблокувати заказчика
        from user.services import BlockService

        BlockService.auto_block_employer_no_group(vacancy.owner)

        # 6. Надіслати повідомлення про блокировку заказчику
        from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

        try:
            bot.send_message(
                vacancy.owner.id,
                CallVacancyTelegramTextFormatter.auto_block_message(reason="ви не зайшли у групу вакансії"),
            )
        except Exception:
            sentry_sdk.capture_exception()

        logger.info(
            "employer_blocked_no_group",
            extra={"vacancy_id": vacancy_id, "user_id": vacancy.owner.id},
        )


def _delete_invite_message(vacancy):
    """Видалити повідомлення-запрошення з чату бота."""
    msg_id = (vacancy.extra or {}).get("employer_invite_msg_id")
    if msg_id:
        try:
            bot.delete_message(chat_id=vacancy.owner.id, message_id=msg_id)
        except Exception:
            pass
        vacancy.extra.pop("employer_invite_msg_id", None)
        vacancy.save(update_fields=["extra"])


def _delete_all_vacancy_messages(vacancy):
    """Видалити всі сервісні повідомлення цієї вакансії з бота заказчика."""
    if not vacancy.extra:
        return

    owner_id = vacancy.owner.id
    keys_to_delete = []

    for key in ["employer_invite_msg_id", "created_msg_id", "approved_msg_id"]:
        msg_id = vacancy.extra.get(key)
        if msg_id:
            try:
                bot.delete_message(chat_id=owner_id, message_id=msg_id)
            except Exception:
                pass
            keys_to_delete.append(key)

    invites = vacancy.extra.get("apply_invite_msg_ids", {})
    for user_id_str, msg_id in invites.items():
        try:
            bot.delete_message(chat_id=int(user_id_str), message_id=msg_id)
        except Exception:
            pass
    if invites:
        keys_to_delete.append("apply_invite_msg_ids")

    for key in keys_to_delete:
        vacancy.extra.pop(key, None)
    vacancy.save(update_fields=["extra"])
