import base64
import json

from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from telegram.handlers.bot_instance import bot
from telegram.service.common import get_payload_url
from user.models import UserFeedback
from .common import get_admin_url
from vacancy.models import Vacancy


def admin_vacancy_reply_markup(vacancy: Vacancy) -> InlineKeyboardMarkup:
    url = settings.BASE_URL.rstrip('/') + reverse('work:admin_moderate_vacancy', kwargs={'vacancy_id': vacancy.pk})
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text=_('Переглянути вакансію'), web_app=WebAppInfo(url=url)))
    return markup

def channel_vacancy_reply_markup(vacancy: Vacancy) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    if vacancy.group and vacancy.group.invite_link:
        markup.add(InlineKeyboardButton(text=_('Apply for vacancy'), url=vacancy.group.invite_link, style='danger'))
    return markup

def admin_vacancy_feedback_reply_markup(feedback: UserFeedback) -> InlineKeyboardMarkup:
    url = settings.BASE_URL.rstrip('/') + get_admin_url(feedback)
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text=_('View feedback'), web_app=WebAppInfo(url=url)))
    return markup

def group_url_feedback_reply_markup(vacancy: Vacancy) -> InlineKeyboardMarkup:
    payload = {
        "type": 'feedback',
        'vacancy_id': vacancy.pk,
    }
    url = get_payload_url(payload=payload)
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text=_('Надіслати відгук'), url=url, style='primary'))
    return markup

def group_webapp_feedback_reply_markup(vacancy: Vacancy) -> InlineKeyboardMarkup:
    url = settings.BASE_URL.rstrip('/') + reverse('vacancy:user_list', kwargs={'pk': vacancy.pk})
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text=_('Надіслати відгук'), web_app=WebAppInfo(url=url), style='primary'))
    return markup