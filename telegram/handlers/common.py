from typing import Any

from django.conf import settings
from django.utils.translation import gettext as _
from telebot.callback_data import CallbackData, CallbackDataFilter
from telebot.types import CallbackQuery, WebAppInfo
from telebot.types import InlineKeyboardButton as IKB

from telegram.choices import CallStatus, CallType


class F:
    def __init__(self, data_filter: CallbackDataFilter):
        self.data_filter = data_filter

    def __call__(self, callback: CallbackQuery, **kwargs: dict[str, Any]) -> bool:
        return self.data_filter.check(callback)


class CallbackStorage:
    menu = CallbackData("name", prefix="menu")
    work_role = CallbackData("role", prefix="work_role")
    language = CallbackData("code", prefix="lang")
    call_handler = CallbackData("call_type", "status", "vacancy_id", prefix="call_handler")

    invoice_payload = CallbackData("vacancy_id", "amount", prefix="invoice_payload")


class ButtonStorage:
    @staticmethod
    def menu_start(label=None):
        return IKB(label or _("Main page"), callback_data=CallbackStorage.menu.new(name="start"))

    @staticmethod
    def menu(label=None, menu_name="start"):
        return IKB(label or _("Main page"), callback_data=CallbackStorage.menu.new(name=menu_name))

    @staticmethod
    def menu_language(label=None):
        return IKB(label or "🌐 " + _("Language"), callback_data=CallbackStorage.menu.new(name="language"))

    @staticmethod
    def work_role(label, role):
        return IKB(label, callback_data=CallbackStorage.work_role.new(role=role))

    @staticmethod
    def web_app(label=None, url=settings.BASE_URL):
        return IKB(label or _("Open the app"), web_app=WebAppInfo(url=url))

    @staticmethod
    def before_start_call_confirm_btn(vacancy_id, label=None):
        return IKB(
            label or _("Confirm"),
            callback_data=CallbackStorage.call_handler.new(
                call_type=CallType.BEFORE_START.value, status=CallStatus.CONFIRM.value, vacancy_id=vacancy_id
            ),
        )

    @staticmethod
    def pay(label):
        return IKB(label, pay=True)
