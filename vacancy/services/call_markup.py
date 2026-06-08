from django.conf import settings
from django.urls import reverse
from telebot.types import InlineKeyboardButton as IKB
from telebot.types import InlineKeyboardMarkup

from telegram.choices import CallStatus, CallType
from telegram.handlers.common import ButtonStorage, CallbackStorage
from vacancy.models import Vacancy


def get_vacancy_my_list_markup() -> InlineKeyboardMarkup:
    """'До поточних заявок' WebApp button for vacancy-approved notification."""
    markup = InlineKeyboardMarkup()
    markup.row(
        ButtonStorage.web_app(
            label="До поточних заявок",
            url=settings.BASE_URL.rstrip("/") + reverse("vacancy:my_list"),
        )
    )
    return markup


def get_before_start_call_markup(vacancy: Vacancy, **kwargs):
    markup = InlineKeyboardMarkup()
    markup.row(
        IKB(
            "Підтвердити",
            callback_data=CallbackStorage.call_handler.new(
                call_type=CallType.BEFORE_START.value,
                status=CallStatus.CONFIRM.value,
                vacancy_id=vacancy.id,
            ),
        ),
        IKB(
            "Відміна",
            callback_data=CallbackStorage.call_handler.new(
                call_type=CallType.BEFORE_START.value,
                status=CallStatus.REJECT.value,
                vacancy_id=vacancy.id,
            ),
        ),
    )
    return markup


def get_start_call_markup(vacancy: Vacancy, **kwargs):
    markup = InlineKeyboardMarkup()
    markup.row(
        ButtonStorage.web_app(
            label="Підтвердити перше опитування",
            url=settings.BASE_URL.rstrip("/") + reverse("vacancy:detail", args=[vacancy.id]) + "?focus=rollcall",
        )
    )
    return markup


def get_final_call_markup(vacancy: Vacancy, **kwargs):
    markup = InlineKeyboardMarkup()
    markup.row(
        ButtonStorage.web_app(
            label="Підтвердити друге опитування",
            url=settings.BASE_URL.rstrip("/") + reverse("vacancy:detail", args=[vacancy.id]) + "?focus=rollcall",
        )
    )
    return markup


def get_final_call_success_markup(**kwargs):
    markup = InlineKeyboardMarkup()
    markup.row(
        ButtonStorage.pay(
            label="Сплатити рахунок",
        )
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
            label="Перейти до переклички",
            url=settings.BASE_URL.rstrip("/") + reverse("vacancy:detail", args=[vacancy.id]) + "?focus=rollcall",
        )
    )
    return markup


def get_renewal_offer_markup(vacancy: Vacancy) -> InlineKeyboardMarkup:
    """Так/Відмовитись buttons sent to employer after payment (renewal offer)."""
    markup = InlineKeyboardMarkup()
    markup.row(
        IKB(
            "Так, бажаю",
            callback_data=CallbackStorage.call_handler.new(
                call_type=CallType.RENEWAL_EMPLOYER.value,
                status=CallStatus.CONFIRM.value,
                vacancy_id=vacancy.id,
            ),
        ),
        IKB(
            "Відмовитись",
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
            "Так",
            callback_data=CallbackStorage.call_handler.new(
                call_type=CallType.RENEWAL_WORKER.value,
                status=CallStatus.CONFIRM.value,
                vacancy_id=vacancy.id,
            ),
        ),
        IKB(
            "Відмовитись",
            callback_data=CallbackStorage.call_handler.new(
                call_type=CallType.RENEWAL_WORKER.value,
                status=CallStatus.REJECT.value,
                vacancy_id=vacancy.id,
            ),
        ),
    )
    return markup


def get_admin_check_rollcall_markup(
    vacancy: Vacancy, call_type: CallType = CallType.AFTER_START
) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    markup.row(
        ButtonStorage.web_app(
            label="Перевірити перекличку",
            url=settings.BASE_URL.rstrip("/") + reverse("vacancy:call", args=[vacancy.id, call_type.value]),
        )
    )
    return markup


def get_worker_join_confirm_markup(vacancy: Vacancy) -> InlineKeyboardMarkup:
    """Confirm / Reject buttons sent to worker after joining the group."""
    markup = InlineKeyboardMarkup()
    markup.row(
        IKB(
            "Підтвердити",
            callback_data=CallbackStorage.call_handler.new(
                call_type=CallType.WORKER_JOIN_CONFIRM.value,
                status=CallStatus.CONFIRM.value,
                vacancy_id=vacancy.id,
            ),
        ),
        IKB(
            "Відміна",
            callback_data=CallbackStorage.call_handler.new(
                call_type=CallType.WORKER_JOIN_CONFIRM.value,
                status=CallStatus.REJECT.value,
                vacancy_id=vacancy.id,
            ),
        ),
    )
    return markup


def get_admin_disputed_rollcall_markup(vacancy: Vacancy) -> InlineKeyboardMarkup:
    """Admin keyboard for a disputed 2nd rollcall.

    Two buttons:
    - "Підтвердити кількість" — admin confirms current count (finalizes).
    - "Редагувати кількість" — admin opens vacancy detail form to edit.
    """
    from telegram.handlers.common import CallbackStorage

    markup = InlineKeyboardMarkup()
    markup.row(
        IKB(
            "Підтвердити кількість",
            callback_data=CallbackStorage.disputed_action.new(action="confirm", vacancy_id=vacancy.id),
        ),
        IKB(
            "Редагувати кількість",
            callback_data=CallbackStorage.disputed_action.new(action="edit", vacancy_id=vacancy.id),
        ),
    )
    return markup


def get_admin_unblock_employer_modal_markup(vacancy: Vacancy) -> InlineKeyboardMarkup:
    """Yes/No modal: unblock the employer after confirming count=0?"""
    from telegram.handlers.common import CallbackStorage

    markup = InlineKeyboardMarkup()
    markup.row(
        IKB(
            "Так",
            callback_data=CallbackStorage.disputed_action.new(action="unblock_yes", vacancy_id=vacancy.id),
        ),
        IKB(
            "Ні",
            callback_data=CallbackStorage.disputed_action.new(action="unblock_no", vacancy_id=vacancy.id),
        ),
    )
    return markup
