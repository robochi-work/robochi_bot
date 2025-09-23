from typing import Any

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from telebot.types import CallbackQuery, InlineKeyboardMarkup
from django.utils.translation import gettext as _

from telegram.choices import CallType, CallStatus
from telegram.handlers.bot_instance import bot
from telegram.handlers.common import CallbackStorage as Storage, F, ButtonStorage
from telegram.handlers.messages.commands import start
from telegram.handlers.utils import user_required
from vacancy.models import Vacancy, VacancyUserCall
from work.choices import WorkProfileRole
from work.service.work_profile import WorkProfileService
from user.models import User



@bot.callback_query_handler(func=F(Storage.call_handler.filter()))
@user_required
def confirm_before_start_call(callback: CallbackQuery, user: User, **kwargs: dict[str, Any]) -> None:
    data = Storage.call_handler.parse(callback.data)
    vacancy: Vacancy = Vacancy.objects.get(id=data['vacancy_id'])
    try:
        vacancy_user = vacancy.users.get(user=user)
        user_call_data, created = VacancyUserCall.objects.update_or_create(
            vacancy_user=vacancy_user,
            defaults={
                'status': data['status'],
                'call_type': data['call_type'],
            }
        )
        bot.delete_message(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
        )
        bot.send_message(
            chat_id=callback.message.chat.id,
            text=_('Answer saved')
        )
    except ObjectDoesNotExist as ex:
        bot.send_message(
            chat_id=callback.message.chat.id,
            text=_('You are no longer a participant in this vacancy.')
        )
