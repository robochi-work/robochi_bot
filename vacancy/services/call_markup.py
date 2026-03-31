from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton as IKB

from service.common import get_admin_url
from telegram.choices import CallType, CallStatus
from telegram.handlers.common import ButtonStorage, CallbackStorage
from vacancy.models import Vacancy


def get_vacancy_my_list_markup() -> InlineKeyboardMarkup:
    """'До поточних заявок' WebApp button for vacancy-approved notification."""
    markup = InlineKeyboardMarkup()
    markup.row(
        ButtonStorage.web_app(
            label='До поточних заявок',
            url=settings.BASE_URL.rstrip('/') + reverse('vacancy:my_list'),
        )
    )
    return markup


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


def get_rollcall_reminder_markup(vacancy: Vacancy, call_type: CallType) -> InlineKeyboardMarkup:
    """'Go to rollcall' WebApp button sent as reminder to vacancy owner."""
    markup = InlineKeyboardMarkup()
    markup.row(
        ButtonStorage.web_app(
            label=_('Go to rollcall'),
            url=settings.BASE_URL.rstrip('/') + reverse(
                'vacancy:pre_call', args=[vacancy.id, call_type.value]
            ),
        )
    )
    return markup


def get_renewal_offer_markup(vacancy: Vacancy) -> InlineKeyboardMarkup:
    """Так/Відмовитись buttons sent to employer after payment (renewal offer)."""
    markup = InlineKeyboardMarkup()
    markup.row(
        IKB(
            'Так, бажаю',
            callback_data=CallbackStorage.call_handler.new(
                call_type=CallType.RENEWAL_EMPLOYER.value,
                status=CallStatus.CONFIRM.value,
                vacancy_id=vacancy.id,
            ),
        ),
        IKB(
            'Відмовитись',
            callback_data=CallbackStorage.call_handler.new(
                call_type=CallType.RENEWAL_EMPLOYER.value,
                status=CallStatus.REJECT.value,
                vacancy_id=vacancy.id,
            ),
        ),
    )
    return markup


def get_renewal_worker_markup(vacancy: Vacancy) -> InlineKeyboardMarkup:
    """Так/Відмовитись buttons sent to workers for tomorrow confirmation."""
    markup = InlineKeyboardMarkup()
    markup.row(
        IKB(
            'Так',
            callback_data=CallbackStorage.call_handler.new(
                call_type=CallType.RENEWAL_WORKER.value,
                status=CallStatus.CONFIRM.value,
                vacancy_id=vacancy.id,
            ),
        ),
        IKB(
            'Відмовитись',
            callback_data=CallbackStorage.call_handler.new(
                call_type=CallType.RENEWAL_WORKER.value,
                status=CallStatus.REJECT.value,
                vacancy_id=vacancy.id,
            ),
        ),
    )
    return markup


def get_worker_join_confirm_markup(vacancy: Vacancy) -> InlineKeyboardMarkup:
    """Confirm / Reject buttons sent to worker after joining the group."""
    markup = InlineKeyboardMarkup()
    markup.row(
        IKB(
            _('Confirm'),
            callback_data=CallbackStorage.call_handler.new(
                call_type=CallType.WORKER_JOIN_CONFIRM.value,
                status=CallStatus.CONFIRM.value,
                vacancy_id=vacancy.id,
            ),
        ),
        IKB(
            _('Reject'),
            callback_data=CallbackStorage.call_handler.new(
                call_type=CallType.WORKER_JOIN_CONFIRM.value,
                status=CallStatus.REJECT.value,
                vacancy_id=vacancy.id,
            ),
        ),
    )
    return markup