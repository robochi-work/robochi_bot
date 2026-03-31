from typing import Any

import sentry_sdk
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


@bot.callback_query_handler(func=F(Storage.call_handler.filter()))
@user_required
def confirm_before_start_call(callback: CallbackQuery, user: User, **kwargs: dict[str, Any]) -> None:
    data = Storage.call_handler.parse(callback.data)
    vacancy: Vacancy = Vacancy.objects.get(id=data["vacancy_id"])

    # --- Renewal employer flow (owner is not a VacancyUser) ---
    if data["call_type"] == CallType.RENEWAL_EMPLOYER.value:
        bot.delete_message(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
        )
        if data["status"] == CallStatus.CONFIRM.value:
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
                bot.send_message(
                    chat_id=callback.message.chat.id,
                    text="Напишіть актуальний номер телефону",
                )
            else:  # REJECT
                if vacancy.group:
                    GroupService.kick_user(chat_id=vacancy.group.id, user_id=user.id)
                user.is_active = False
                user.save(update_fields=["is_active"])
                bot.send_message(
                    chat_id=callback.message.chat.id,
                    text="Ви відмовились від вакансії.",
                )
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
        bot.delete_message(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
        )
        bot.send_message(chat_id=callback.message.chat.id, text=_("Answer saved"))
    except ObjectDoesNotExist:
        bot.send_message(chat_id=callback.message.chat.id, text=_("You are no longer a participant in this vacancy."))
