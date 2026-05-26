from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from user.models import UserFeedback
from vacancy.models import Vacancy

from .common import get_admin_url


def admin_vacancy_reply_markup(vacancy: Vacancy) -> InlineKeyboardMarkup:
    url = settings.BASE_URL.rstrip("/") + reverse("work:admin_moderate_vacancy", kwargs={"vacancy_id": vacancy.pk})
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text=_("Переглянути вакансію"), web_app=WebAppInfo(url=url)))
    return markup


def channel_vacancy_reply_markup(vacancy: Vacancy) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton(
            text=_("Apply for vacancy"),
            callback_data=f"apply:{vacancy.id}",
            style="danger",
        )
    )
    return markup


def admin_vacancy_feedback_reply_markup(feedback: UserFeedback) -> InlineKeyboardMarkup:
    url = settings.BASE_URL.rstrip("/") + get_admin_url(feedback)
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text=_("View feedback"), web_app=WebAppInfo(url=url)))
    return markup


def group_url_feedback_reply_markup(vacancy: Vacancy) -> InlineKeyboardMarkup:
    url = f"https://t.me/riznorobochi_ua_bot?startapp=fb_{vacancy.pk}"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text=_("Відгуки/Контакти"), url=url))
    return markup


def group_webapp_feedback_reply_markup(vacancy: Vacancy) -> InlineKeyboardMarkup:
    url = f"https://t.me/riznorobochi_ua_bot?startapp=fb_{vacancy.pk}"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text=_("Відгуки/Контакти"), url=url))
    return markup
