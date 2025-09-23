from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _
from telebot.types import InlineKeyboardMarkup

from service.common import get_admin_url
from telegram.choices import CallType
from telegram.handlers.common import ButtonStorage
from vacancy.models import Vacancy


def get_before_start_call_markup(vacancy: Vacancy, **kwargs):
    markup = InlineKeyboardMarkup()
    markup.row(
        ButtonStorage.before_start_call_confirm_btn(
            vacancy_id=vacancy.id,
        )
    )

    return markup

def get_start_call_markup(vacancy: Vacancy, **kwargs):
    markup = InlineKeyboardMarkup()
    markup.row(
        ButtonStorage.web_app(
            label=_('Confirm first call'),
            url=settings.BASE_URL.rstrip('/') + reverse('vacancy:pre_call', args=[vacancy.id, CallType.START.value]),
        )
    )
    return markup

def get_final_call_markup(vacancy: Vacancy, **kwargs):
    markup = InlineKeyboardMarkup()
    markup.row(
        ButtonStorage.web_app(
            label=_('Confirm second call'),
            url=settings.BASE_URL.rstrip('/') + reverse('vacancy:pre_call', args=[vacancy.id, CallType.AFTER_START.value]),
        )
    )
    return markup

def get_final_call_success_markup(**kwargs):
    markup = InlineKeyboardMarkup()
    markup.row(
        ButtonStorage.pay(label=_('Pay'),)
    )
    return markup

def get_after_start_call_markup(**kwargs):
    markup = InlineKeyboardMarkup()
    return markup