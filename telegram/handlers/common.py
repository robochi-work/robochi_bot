from typing import Any
from django.conf import settings
from django.utils.translation import gettext as _
from telebot.callback_data import CallbackData, CallbackDataFilter
from telebot.types import CallbackQuery, InlineKeyboardButton as IKB, WebAppInfo

from telegram.choices import CallType, CallStatus


class F:
    def __init__(self, data_filter: CallbackDataFilter):
        self.data_filter = data_filter

    def __call__(self, callback: CallbackQuery, **kwargs: dict[str, Any]) -> bool:
        return self.data_filter.check(callback)

class CallbackStorage:
    menu = CallbackData('name', prefix='menu')
    work_role = CallbackData('role', prefix='work_role')
    language = CallbackData('code', prefix='lang')
    call_handler = CallbackData('call_type', 'status', 'vacancy_id', prefix='call_handler')

    invoice_payload = CallbackData('vacancy_id', 'amount', prefix='invoice_payload')


class ButtonStorage:
    menu_start = lambda label=None: IKB(label or _('Main page'), callback_data=CallbackStorage.menu.new(name='start'))
    menu = lambda label=None, menu_name='start': IKB(label or _('Main page'), callback_data=CallbackStorage.menu.new(name=menu_name))
    menu_language = lambda label=None: IKB(label or '🌐 ' + _('Language'), callback_data=CallbackStorage.menu.new(name='language'))
    work_role = lambda label, role: IKB(label, callback_data=CallbackStorage.work_role.new(role=role))
    web_app = lambda label=None, url=settings.BASE_URL: IKB(label or _('Open the app'), web_app=WebAppInfo(url=url))
    before_start_call_confirm_btn = lambda vacancy_id, label='Подтвердить': IKB(label, callback_data=CallbackStorage.call_handler.new(call_type=CallType.BEFORE_START.value, status=CallStatus.CONFIRM.value, vacancy_id=vacancy_id))
    pay = lambda label: IKB(label, pay=True)

