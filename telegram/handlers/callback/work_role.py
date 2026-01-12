from typing import Any

from django.conf import settings
from django.urls import reverse
from telebot.types import CallbackQuery, InlineKeyboardMarkup
from django.utils.translation import gettext as _
from telegram.handlers.bot_instance import bot
from telegram.handlers.common import CallbackStorage as Storage, F, ButtonStorage
from telegram.handlers.messages.commands import start
from telegram.handlers.utils import user_required
from work.choices import WorkProfileRole
from work.service.work_profile import WorkProfileService
from user.models import User



@bot.callback_query_handler(func=F(Storage.work_role.filter()))
@user_required
def set_work_role(callback: CallbackQuery, user: User, **kwargs: dict[str, Any]) -> None:
    chat_id = callback.message.chat.id
    data = Storage.work_role.parse(callback.data)
    service = WorkProfileService(user=user)
    profile = service.get_profile()

    markup = InlineKeyboardMarkup()
    markup.add(ButtonStorage.web_app(label=_('Fill out the form'), url=settings.BASE_URL.rstrip('/') + reverse('work:wizard')))

    if profile.role is not None:
        bot.send_message(chat_id, text=_('You can change the role only through the administrator'))
    else:
        match data.get('role'):
            case WorkProfileRole.WORKER.value:
                service.set_role(WorkProfileRole.WORKER)
            case WorkProfileRole.EMPLOYER.value:
                service.set_role(WorkProfileRole.EMPLOYER)
            case _:
                bot.send_message(chat_id, text=_('Unknown role'))

    bot.delete_message(chat_id=chat_id, message_id=callback.message.message_id)
    start(callback)