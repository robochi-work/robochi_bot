import logging
from typing import Any

import sentry_sdk
import telebot
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from django.utils.translation import gettext as _
from telebot.types import CallbackQuery

from telegram.choices import CallStatus, CallType
from telegram.handlers.bot_instance import bot
from telegram.handlers.common import CallbackStorage as Storage
from telegram.handlers.common import F
from telegram.handlers.utils import user_required
from telegram.service.group import GroupService
from user.models import User
from vacancy.models import Vacancy, VacancyUserCall

logger = logging.getLogger(__name__)


@bot.callback_query_handler(func=F(Storage.call_handler.filter()))
@user_required
def confirm_before_start_call(callback: CallbackQuery, user: User, **kwargs: dict[str, Any]) -> None:
    data = Storage.call_handler.parse(callback.data)
    vacancy: Vacancy = Vacancy.objects.select_related("group", "owner").get(id=data["vacancy_id"])

    # --- Renewal employer flow (owner is not a VacancyUser) ---
    if data["call_type"] == CallType.RENEWAL_EMPLOYER.value:
        bot.delete_message(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
        )
        if data["status"] == CallStatus.CONFIRM.value:
            logger.info(
                "call_confirmed", extra={"user_id": user.id, "vacancy_id": vacancy.id, "call_type": data["call_type"]}
            )
            vacancy.extra["renewal_accepted"] = True
            vacancy.extra["renewal_offered"] = True
            vacancy.save(update_fields=["extra"])
            from django.conf import settings

            url = settings.BASE_URL.rstrip("/") + reverse("vacancy:resume_search", args=[vacancy.id])
            from telebot.types import InlineKeyboardMarkup

            from telegram.handlers.common import ButtonStorage

            markup = InlineKeyboardMarkup()
            markup.row(ButtonStorage.web_app(label="Редагувати вакансію на завтра", url=url))
            bot.send_message(
                chat_id=callback.message.chat.id,
                text="Відредагуйте вакансію на завтра. Адреса та посилання на карту залишаються без змін.",
                reply_markup=markup,
            )
        else:  # REJECT
            logger.info(
                "call_declined", extra={"user_id": user.id, "vacancy_id": vacancy.id, "call_type": data["call_type"]}
            )
            from django.utils import timezone as tz

            vacancy.extra["renewal_declined"] = True
            vacancy.extra["renewal_offered"] = True
            vacancy.closed_at = tz.now()
            vacancy.save(update_fields=["extra", "closed_at"])
            if vacancy.group:
                try:
                    GroupService.kick_user(chat_id=vacancy.group.id, user_id=user.id)
                except Exception:
                    sentry_sdk.capture_exception()
            bot.send_message(
                chat_id=callback.message.chat.id,
                text="Вакансію на завтра скасовано. Через 3 години групу буде закрито.",
            )
        return

    try:
        vacancy_user = vacancy.users.get(user=user)

        # --- Join confirmation flow ---
        if data["call_type"] == CallType.WORKER_JOIN_CONFIRM.value:
            VacancyUserCall.objects.filter(
                vacancy_user=vacancy_user,
                call_type=CallType.WORKER_JOIN_CONFIRM.value,
            ).update(status=data["status"])

            bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
            )

            if data["status"] == CallStatus.CONFIRM.value:
                logger.info(
                    "call_confirmed",
                    extra={"user_id": user.id, "vacancy_id": vacancy.id, "call_type": data["call_type"]},
                )
                # Phone confirmation flow
                from vacancy.models import VacancyContactPhone

                phone_exists = VacancyContactPhone.objects.filter(vacancy=vacancy, user=user).exists()

                if phone_exists:
                    # Phone already saved for this vacancy — send group invite
                    from vacancy.services.worker_invite import send_worker_group_invite

                    send_worker_group_invite(user, vacancy)
                elif user.contact_phone:
                    # User has saved contact phone — ask to confirm or change
                    import json as _json

                    confirm_data = _json.dumps({"t": "phone_confirm", "v": vacancy.id, "s": "confirm"})
                    change_data = _json.dumps({"t": "phone_confirm", "v": vacancy.id, "s": "change"})
                    markup = telebot.types.InlineKeyboardMarkup()
                    markup.row(
                        telebot.types.InlineKeyboardButton("Підтвердити", callback_data=confirm_data),
                        telebot.types.InlineKeyboardButton("Змінити", callback_data=change_data),
                    )
                    bot.send_message(
                        chat_id=callback.message.chat.id,
                        text=f"Ваш контактний номер: {user.contact_phone}",
                        reply_markup=markup,
                    )
                else:
                    # No contact phone at all — ask to enter
                    bot.send_message(
                        chat_id=callback.message.chat.id,
                        text="Напишіть актуальний номер телефону",
                    )
            else:  # REJECT
                logger.info(
                    "call_declined",
                    extra={"user_id": user.id, "vacancy_id": vacancy.id, "call_type": data["call_type"]},
                )
                # Worker is NOT in the group yet — just mark as LEFT
                from telegram.models import Status
                from vacancy.models import VacancyUser

                VacancyUser.objects.filter(user=user, vacancy=vacancy).update(status=Status.LEFT)
                # Clean up contact phone so re-apply starts fresh
                from vacancy.models import VacancyContactPhone

                VacancyContactPhone.objects.filter(vacancy=vacancy, user=user).delete()
                bot.send_message(
                    chat_id=callback.message.chat.id,
                    text="Ви відмовились від вакансії.",
                )
                # Send cabinet link
                from telegram.handlers.messages.commands import _send_cabinet_message

                _send_cabinet_message(callback.message)
            return

        # --- Renewal worker flow ---
        if data["call_type"] == CallType.RENEWAL_WORKER.value:
            bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
            )
            if data["status"] == CallStatus.CONFIRM.value:
                VacancyUserCall.objects.filter(
                    vacancy_user=vacancy_user,
                    call_type=CallType.RENEWAL_WORKER.value,
                ).update(status=CallStatus.CONFIRM.value)
                bot.send_message(
                    chat_id=callback.message.chat.id,
                    text=_("Answer saved"),
                )
            else:  # REJECT
                VacancyUserCall.objects.filter(
                    vacancy_user=vacancy_user,
                    call_type=CallType.RENEWAL_WORKER.value,
                ).update(status=CallStatus.REJECT.value)
                if vacancy.group:
                    try:
                        GroupService.kick_user(chat_id=vacancy.group.id, user_id=user.id)
                    except Exception:
                        sentry_sdk.capture_exception()
                bot.send_message(
                    chat_id=callback.message.chat.id,
                    text="Ви відмовились від вакансії на завтра.",
                )
            return

        # --- Standard roll-call flow ---
        user_call_data, created = VacancyUserCall.objects.update_or_create(
            vacancy_user=vacancy_user,
            defaults={
                "status": data["status"],
                "call_type": data["call_type"],
            },
        )
        if data["status"] == CallStatus.CONFIRM.value:
            logger.info(
                "call_confirmed", extra={"user_id": user.id, "vacancy_id": vacancy.id, "call_type": data["call_type"]}
            )
        else:
            logger.info(
                "call_declined", extra={"user_id": user.id, "vacancy_id": vacancy.id, "call_type": data["call_type"]}
            )
        bot.delete_message(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
        )
        if data["call_type"] == CallType.BEFORE_START.value:
            if data["status"] == CallStatus.CONFIRM.value:
                bot.send_message(
                    chat_id=callback.message.chat.id,
                    text=_("Answer saved"),
                )
                # Контакт замовника після підтвердження переклички за 2 години
                try:
                    from vacancy.models import VacancyContactPhone

                    phone_obj = VacancyContactPhone.objects.filter(vacancy=vacancy, user=vacancy.owner).first()
                    phone = phone_obj.phone if phone_obj else None
                except Exception:
                    phone = None
                if phone:
                    bot.send_message(
                        chat_id=callback.message.chat.id,
                        text=f"Контактний телефон замовника за вакансією {vacancy.address}: {phone}",
                    )
                return
            else:
                # REJECT або ігнор — кік з групи
                if vacancy.group:
                    try:
                        GroupService.kick_user(chat_id=vacancy.group.id, user_id=user.id)
                    except Exception:
                        sentry_sdk.capture_exception()
                bot.send_message(
                    chat_id=callback.message.chat.id,
                    text="Ви відмовились від вакансії.",
                )
                return

        bot.send_message(chat_id=callback.message.chat.id, text=_("Answer saved"))
    except ObjectDoesNotExist:
        bot.send_message(chat_id=callback.message.chat.id, text=_("You are no longer a participant in this vacancy."))
