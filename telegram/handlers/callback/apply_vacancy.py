import logging

import sentry_sdk
from telebot.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from telegram.choices import Status
from telegram.handlers.bot_instance import bot
from user.models import User
from user.services import BlockService
from vacancy.choices import GENDER_ANY, STATUS_ACTIVE, STATUS_APPROVED
from vacancy.models import Vacancy, VacancyUser
from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

logger = logging.getLogger(__name__)


@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("apply:"))
def handle_apply_vacancy(call: CallbackQuery):
    """Handle 'Я ГОТОВИЙ ПРАЦЮВАТИ' button press — run all checks before granting access."""
    try:
        vacancy_id = int(call.data.split(":")[1])
    except (IndexError, ValueError):
        bot.answer_callback_query(call.id, text="Помилка. Спробуйте ще раз.", show_alert=True)
        return

    try:
        user, _ = User.objects.update_or_create(
            id=call.from_user.id,
            defaults={"username": call.from_user.username},
        )

        # Admin always passes
        if user.is_staff:
            _send_invite(call, vacancy_id, user)
            return

        # Permanent block
        if BlockService.is_permanently_blocked(user):
            bot.answer_callback_query(
                call.id,
                show_alert=True,
                text=CallVacancyTelegramTextFormatter.auto_block_message(reason="постійне блокування"),
            )
            return

        # Temporary block
        if BlockService.is_temporarily_blocked(user):
            bot.answer_callback_query(
                call.id,
                text="Ви не можете брати участь у вакансіях. Ви заблоковані.",
                show_alert=True,
            )
            return

        # Legacy is_active=False
        if not user.is_active:
            bot.answer_callback_query(
                call.id,
                text="Ви не можете брати участь у вакансіях. Ви заблоковані.",
                show_alert=True,
            )
            return

        # Not registered
        work_profile = getattr(user, "work_profile", None)
        if not work_profile or not work_profile.role:
            bot.answer_callback_query(
                call.id,
                show_alert=True,
                text="Щоб приєднатися до вакансії, спочатку зареєструйтесь у боті. Натисніть /start.",
            )
            return

        try:
            vacancy = Vacancy.objects.select_related("group", "owner").get(
                id=vacancy_id,
                status__in=[STATUS_APPROVED, STATUS_ACTIVE],
            )
        except Vacancy.DoesNotExist:
            bot.answer_callback_query(call.id, text="Вакансію не знайдено або вона вже закрита.", show_alert=True)
            return

        # Owner always passes
        if vacancy.owner == user:
            _send_invite(call, vacancy_id, user, is_owner=True)
            return

        # Employer cannot join another employer's vacancy
        if work_profile.role == "employer":
            bot.answer_callback_query(
                call.id,
                show_alert=True,
                text="Ви роботодавець. Ви не можете приєднатися до чужої вакансії.",
            )
            logger.warning(
                "apply_declined",
                extra={"user_id": user.id, "vacancy_id": vacancy_id, "reason": "employer_not_owner"},
            )
            return

        # Already in another active vacancy
        if (
            VacancyUser.objects.filter(
                user=user,
                status=Status.MEMBER,
                vacancy__status__in=[STATUS_APPROVED, STATUS_ACTIVE],
            )
            .exclude(vacancy=vacancy)
            .exists()
        ):
            bot.answer_callback_query(
                call.id,
                show_alert=True,
                text="Ви вже берете участь в іншій вакансії. Спочатку завершіть поточну.",
            )
            return

        # Group is full
        if vacancy.members.count() >= vacancy.people_count:
            bot.answer_callback_query(
                call.id,
                show_alert=True,
                text="На жаль, всі місця за цією вакансією вже зайняті.",
            )
            return

        # Gender filter
        if vacancy.gender != GENDER_ANY:
            if not user.gender:
                bot.answer_callback_query(
                    call.id,
                    show_alert=True,
                    text="Ваша стать не вказана в профілі. Зверніться до адміністратора.",
                )
                return
            if vacancy.gender != user.gender:
                bot.answer_callback_query(
                    call.id,
                    show_alert=True,
                    text="Ця вакансія призначена для іншої статі.",
                )
                return

        # All checks passed — send invite link
        _send_invite(call, vacancy_id, user)
        logger.info("apply_approved", extra={"user_id": user.id, "vacancy_id": vacancy_id})

    except Exception:
        sentry_sdk.capture_exception()
        bot.answer_callback_query(call.id, text="Сталася помилка. Спробуйте пізніше.", show_alert=True)


def _send_invite(call: CallbackQuery, vacancy_id: int, user: User, is_owner: bool = False):
    """Send group invite link to user in bot DM."""
    try:
        vacancy = Vacancy.objects.select_related("group").get(id=vacancy_id)
        if not vacancy.group or not vacancy.group.invite_link:
            bot.answer_callback_query(call.id, text="Групу вакансії не знайдено.", show_alert=True)
            return

        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton(
                text="Перейти в групу вакансії",
                url=vacancy.group.invite_link,
            )
        )

        role_text = "Роботодавець" if is_owner else "Робітник"
        bot.send_message(
            chat_id=user.id,
            text=f"✅ Вас допущено до вакансії як {role_text}.\nПерейдіть у групу за посиланням нижче:",
            reply_markup=markup,
        )
        bot.answer_callback_query(call.id, text="Посилання відправлено в бот ✅")

    except Exception:
        sentry_sdk.capture_exception()
        bot.answer_callback_query(call.id, text="Помилка відправки посилання.", show_alert=True)
