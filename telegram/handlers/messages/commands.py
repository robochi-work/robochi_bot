import base64
import json
import logging
from typing import Any
from urllib.parse import urlencode

import sentry_sdk
from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _
from telebot import types
from telebot.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)

from telegram.choices import CallStatus, CallType
from telegram.handlers.bot_instance import bot, get_bot
from telegram.handlers.common import ButtonStorage, CallbackStorage, F
from telegram.handlers.common import CallbackStorage as Storage
from telegram.handlers.utils import user_required
from telegram.models import Status
from user.models import User
from user.services import BlockService
from vacancy.choices import STATUS_ACTIVE, STATUS_APPROVED
from vacancy.models import Vacancy, VacancyUser, VacancyUserCall
from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter
from vacancy.services.call_markup import get_worker_join_confirm_markup
from work.choices import WorkProfileRole

logger = logging.getLogger(__name__)


@user_required
def choose_role(message: Message, **kwargs: dict[str, Any]) -> None:
    markup = InlineKeyboardMarkup()
    markup.add(ButtonStorage.work_role(label=str(WorkProfileRole.WORKER.label), role=WorkProfileRole.WORKER.value))
    markup.add(ButtonStorage.work_role(label=str(WorkProfileRole.EMPLOYER.label), role=WorkProfileRole.EMPLOYER.value))

    get_bot().send_message(
        message.chat.id,
        _("Welcome to robochi.work! Choose your role below."),
        reply_markup=markup,
    )


@user_required
def fill_work_account(message: Message, **kwargs: dict[str, Any]) -> None:
    markup = InlineKeyboardMarkup()
    next_path = reverse("work:wizard")
    check_url = reverse("telegram:telegram_check_web_app")
    url = settings.BASE_URL.rstrip("/") + check_url + "?" + urlencode({"next": next_path})
    markup.add(ButtonStorage.web_app(label=_("Fill out the form"), url=url))
    get_bot().send_message(message.chat.id, text=_("You must fill out a work form"), reply_markup=markup)


@user_required
def ask_phone(message: Message, user: User, **kwargs):
    bot = get_bot()
    # Remove WebApp MenuButton so user sees ReplyKeyboard for phone
    try:
        bot.set_chat_menu_button(
            chat_id=message.chat.id,
            menu_button=types.MenuButtonDefault(type="default"),
        )
        bot.delete_my_commands(scope=types.BotCommandScopeChat(chat_id=message.chat.id))
    except Exception as e:
        logger.error(f"RESET_MENU_BUTTON FAILED: {e}")
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add(types.KeyboardButton(_("Надіслати номер телефону"), request_contact=True))
    logger.warning(f"ASK_PHONE CALLED: chat_id={message.chat.id}, user={user.pk}")
    try:
        bot.send_message(
            message.chat.id,
            _("Для продовження надішліть ваш номер телефону:"),
            reply_markup=markup,
            parse_mode=None,
        )
        logger.warning("ASK_PHONE SENT OK")
    except Exception as e:
        logger.error(f"ASK_PHONE FAILED: {e}")


@user_required
def default_start(message: Message, user: User, **kwargs):
    bot = get_bot()
    check_url = reverse("telegram:telegram_check_web_app")
    url = settings.BASE_URL.rstrip("/") + check_url

    # Set MenuButton "ПОЧАТИ" -> WebApp
    try:
        bot.set_chat_menu_button(
            chat_id=message.chat.id,
            menu_button=MenuButtonWebApp(
                type="web_app",
                text="ПОЧАТИ",
                web_app=types.WebAppInfo(url=url),
            ),
        )
    except Exception as e:
        logger.error(f"SET_MENU_BUTTON FAILED: {e}", exc_info=True)

    bot.send_message(
        message.chat.id,
        _("Вітаємо у нашому сервісі!\nНатискайте кнопку ПОЧАТИ нижче."),
    )


def encode_start_param(data: dict) -> str:
    """Кодування словника в safe Base64 для /start payload"""
    json_str = json.dumps(data, separators=(",", ":"))
    return base64.urlsafe_b64encode(json_str.encode()).decode().rstrip("=")


def decode_start_param(encoded: str) -> dict:
    """Декодирование safe Base64 в словарь"""
    padding = "=" * (-len(encoded) % 4)  # Восстанавливаем "="
    decoded_str = base64.urlsafe_b64decode(encoded + padding).decode()
    return json.loads(decoded_str)


def _process_apply_payload(data: dict, message) -> bool:
    """Handle type=apply deep link: create VacancyUser + send join-confirm BEFORE group entry."""
    vacancy_id = data.get("vacancy_id")
    if not vacancy_id:
        return False

    try:
        user = User.objects.get(id=message.from_user.id)
    except User.DoesNotExist:
        return False

    # Owner (employer) — redirect to cabinet, not worker flow
    work_profile = getattr(user, "work_profile", None)
    if work_profile and work_profile.role == "employer":
        _send_cabinet_message(message)
        return True

    try:
        vacancy = Vacancy.objects.select_related("group", "owner").get(
            id=vacancy_id,
            status__in=[STATUS_APPROVED, STATUS_ACTIVE],
        )
    except Vacancy.DoesNotExist:
        get_bot().send_message(message.chat.id, "Вакансію не знайдено або вона вже закрита.")
        return True

    # Already has VacancyUser for THIS vacancy — re-send confirm or redirect
    existing_vu = VacancyUser.objects.filter(user=user, vacancy=vacancy, status=Status.MEMBER).first()
    if existing_vu:
        # Check if already confirmed (has CONFIRM call)
        confirmed = VacancyUserCall.objects.filter(
            vacancy_user=existing_vu,
            call_type=CallType.WORKER_JOIN_CONFIRM.value,
            status=CallStatus.CONFIRM.value,
        ).exists()
        if confirmed:
            # Already confirmed — send cabinet link
            _send_cabinet_message(message)
            return True
        # Not yet confirmed — re-send confirm message
        pending = VacancyUserCall.objects.filter(
            vacancy_user=existing_vu,
            call_type=CallType.WORKER_JOIN_CONFIRM.value,
            status=CallStatus.SENT.value,
        ).first()
        if pending:
            try:
                get_bot().send_message(
                    chat_id=message.chat.id,
                    text=CallVacancyTelegramTextFormatter(vacancy).worker_join_confirm(),
                    reply_markup=get_worker_join_confirm_markup(vacancy),
                )
            except Exception as e:
                logger.warning(f"_process_apply_payload: re-send confirm failed: {e}")
            return True

    # Check: already in ANOTHER active vacancy
    if (
        VacancyUser.objects.filter(
            user=user,
            status=Status.MEMBER,
            vacancy__status__in=[STATUS_APPROVED, STATUS_ACTIVE],
        )
        .exclude(vacancy=vacancy)
        .exists()
    ):
        get_bot().send_message(
            message.chat.id,
            "Ви вже берете участь в іншій вакансії. Спочатку завершіть поточну.",
        )
        return True

    # Check: group full
    if vacancy.members.count() >= vacancy.people_count:
        get_bot().send_message(message.chat.id, "На жаль, всі місця за цією вакансією вже зайняті.")
        return True

    # Create VacancyUser (MEMBER status but NOT in Telegram group yet)
    vu, _ = VacancyUser.objects.update_or_create(
        user=user,
        vacancy=vacancy,
        defaults={"status": Status.MEMBER.value},
    )

    # Create join-confirm call
    from django.utils import timezone

    VacancyUserCall.objects.update_or_create(
        vacancy_user=vu,
        call_type=CallType.WORKER_JOIN_CONFIRM.value,
        defaults={
            "status": CallStatus.SENT.value,
            "created_at": timezone.now(),
        },
    )

    # Send confirm message
    try:
        get_bot().send_message(
            chat_id=message.chat.id,
            text=CallVacancyTelegramTextFormatter(vacancy).worker_join_confirm(),
            reply_markup=get_worker_join_confirm_markup(vacancy),
        )
    except Exception as e:
        logger.warning(f"_process_apply_payload: send confirm failed: {e}")

    logger.info("apply_confirm_sent", extra={"user_id": user.id, "vacancy_id": vacancy_id})
    return True


def _send_cabinet_message(message):
    """Send 'go to cabinet' message with WebApp button."""
    check_url = reverse("telegram:telegram_check_web_app")
    url = settings.BASE_URL.rstrip("/") + check_url
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton(
            text="Перейти",
            web_app=WebAppInfo(url=url),
        )
    )
    get_bot().send_message(
        chat_id=message.chat.id,
        text="Перейдіть у Власний кабінет— тут ви зможете обрати роботу, "
        "знайти групу Вашої вакансії та отримати підказки користування сервісом.",
        reply_markup=markup,
    )


def process_start_payload(payload: str, message) -> bool:
    try:
        data = decode_start_param(payload)

        if data.get("type") == "feedback":
            url = settings.BASE_URL.rstrip("/") + reverse("vacancy:user_list", kwargs={"pk": data.get("vacancy_id")})
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(text=_("Open"), web_app=WebAppInfo(url=url)))
            get_bot().send_message(message.chat.id, text=_("Надіслати відгук"), reply_markup=markup)
            return True

        elif data.get("type") == "apply":
            return _process_apply_payload(data, message)

        elif data.get("type") == "already_in_vacancy":
            _send_cabinet_message(message)
            return True

        elif data.get("type") == "info":
            send_info(message)
            return True
        else:
            return False

    except Exception:
        return False


@bot.message_handler(commands=["start"])
@bot.callback_query_handler(func=F(CallbackStorage.menu.filter(name="start")))
@user_required
def start(query: Message | CallbackQuery, user: User, **kwargs: dict[str, Any]) -> None:
    if isinstance(query, CallbackQuery):
        message = query.message
    else:
        message = query
    logger.info("start_command", extra={"user_id": message.from_user.id})

    if message.text:
        parts = message.text.split(maxsplit=1)
        if len(parts) > 1:
            result = process_start_payload(parts[1], message)
            if result:
                return

    if BlockService.is_permanently_blocked(user):
        get_bot().send_message(
            message.chat.id,
            "Вас заблоковано у сервісі robochi.work !\nДля розблокування зверніться до Адміністратора- @robochi_work_admin",
        )
        return

    try:
        if not user.phone_number:
            logger.warning("START → ask_phone")
            ask_phone(message, user=user)
        else:
            logger.warning("START → default_start")
            default_start(message, user=user)
    except Exception as e:
        logger.error(f"START FAILED: {type(e).__name__}: {e}", exc_info=True)


@bot.message_handler(commands=["help"])
def admin_help(message):
    logger.info("help_command", extra={"user_id": message.from_user.id})
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text="Написати адміністратору", url="https://t.me/robochi_work_admin"))
    # In groups: reply to user privately, delete command message
    if message.chat.type in ["group", "supergroup"]:
        try:
            bot.send_message(
                message.from_user.id,
                "Натисніть кнопку нижче для зв'язку з адміністратором:",
                reply_markup=markup,
            )
            bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            # User hasn't started bot privately — send in group
            bot.send_message(
                message.chat.id,
                "Натисніть кнопку нижче для зв'язку з адміністратором:",
                reply_markup=markup,
            )
    else:
        bot.send_message(
            message.chat.id,
            "Натисніть кнопку нижче для зв'язку з адміністратором:",
            reply_markup=markup,
        )


@bot.message_handler(commands=["info"])
@bot.callback_query_handler(func=F(Storage.menu.filter()))
def send_info(message):
    if isinstance(message, CallbackQuery):
        message = message.message

    files = [
        "telegram/media/Договір оферти.docx",
        "telegram/media/Політика конфіденційності.docx",
    ]
    for file_path in files:
        try:
            with open(file_path, "rb") as f:
                bot.send_document(
                    chat_id=message.chat.id,
                    document=f,
                )
        except Exception:
            sentry_sdk.capture_exception()
