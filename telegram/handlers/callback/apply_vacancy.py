import logging

import sentry_sdk
from telebot.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from telegram.handlers.bot_instance import bot
from telegram.models import Status
from user.models import User
from user.services import BlockService
from vacancy.choices import GENDER_ANY, STATUS_ACTIVE, STATUS_APPROVED
from vacancy.models import Vacancy, VacancyUser
from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

logger = logging.getLogger(__name__)


@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("apply:"))
def handle_apply_vacancy(call: CallbackQuery):
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

        work_profile = getattr(user, "work_profile", None)

        # 1. Admin — пропускаем все проверки
        if user.is_staff:
            _send_invite(call, vacancy_id, user, role_text="Адміністратор")
            return

        # 2. Постоянная блокировка
        if BlockService.is_permanently_blocked(user):
            bot.answer_callback_query(
                call.id,
                show_alert=True,
                text=CallVacancyTelegramTextFormatter.auto_block_message(reason="постійне блокування"),
            )
            return

        # 3. Временная блокировка
        if BlockService.is_temporarily_blocked(user):
            bot.answer_callback_query(
                call.id, show_alert=True, text="Ви не можете брати участь у вакансіях. Ви заблоковані."
            )
            return

        # 4. Legacy is_active=False
        if not user.is_active:
            bot.answer_callback_query(
                call.id, show_alert=True, text="Ви не можете брати участь у вакансіях. Ви заблоковані."
            )
            return

        # 5. Не зарегистрирован
        if not work_profile or not work_profile.role:
            bot.answer_callback_query(call.id, text="Потрібна реєстрація.", show_alert=True)
            try:
                reg_markup = InlineKeyboardMarkup()
                reg_markup.add(
                    InlineKeyboardButton(
                        text="ЗАРЕЄСТРУВАТИСЬ",
                        url="https://t.me/riznorobochi_ua_bot",
                    )
                )
                bot.send_message(
                    call.from_user.id,
                    "Спочатку зареєструйтеся у нашому сервісі.",
                    reply_markup=reg_markup,
                )
            except Exception:
                sentry_sdk.capture_exception()
            return

        # 6. Получаем вакансию
        try:
            vacancy = Vacancy.objects.select_related("group", "owner").get(
                id=vacancy_id,
                status__in=[STATUS_APPROVED, STATUS_ACTIVE],
            )
        except Vacancy.DoesNotExist:
            bot.answer_callback_query(call.id, show_alert=True, text="Вакансію не знайдено або вона вже закрита.")
            return

        # 7. Owner вакансии
        if vacancy.owner == user:
            _send_invite(call, vacancy_id, user, role_text="Роботодавець")
            return

        # 8. Чужой employer
        if work_profile.role == "employer":
            bot.answer_callback_query(call.id, show_alert=True, text="Ви не можете приєднатися до чужої вакансії.")
            logger.warning(
                "apply_declined", extra={"user_id": user.id, "vacancy_id": vacancy_id, "reason": "employer_not_owner"}
            )
            return

        # 9. Уже в другой вакансии
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
                call.id, show_alert=True, text="Ви вже берете участь в іншій вакансії. Спочатку завершіть поточну."
            )
            return

        # 10. Группа заполнена
        if vacancy.members.count() >= vacancy.people_count:
            bot.answer_callback_query(
                call.id, show_alert=True, text="На жаль, всі місця за цією вакансією вже зайняті."
            )
            return

        # 11-12. Пол
        if vacancy.gender != GENDER_ANY:
            if not user.gender:
                bot.answer_callback_query(
                    call.id, show_alert=True, text="Ваша стать не вказана в профілі. Зверніться до адміністратора."
                )
                return
            if vacancy.gender != user.gender:
                bot.answer_callback_query(call.id, show_alert=True, text="Ця вакансія призначена для іншої статі.")
                return

        # Все проверки пройдены
        _send_invite(call, vacancy_id, user, role_text="Робітник")
        logger.info("apply_approved", extra={"user_id": user.id, "vacancy_id": vacancy_id})

    except Exception:
        sentry_sdk.capture_exception()
        bot.answer_callback_query(call.id, text="Сталася помилка. Спробуйте пізніше.", show_alert=True)


def _send_invite(call: CallbackQuery, vacancy_id: int, user: User, role_text: str = "Робітник"):
    try:
        vacancy = Vacancy.objects.select_related("group").get(id=vacancy_id)
        if not vacancy.group or not vacancy.group.invite_link:
            bot.answer_callback_query(call.id, text="Групу вакансії не знайдено.", show_alert=True)
            return

        invites = vacancy.extra.get("apply_invite_msg_ids", {}) if vacancy.extra else {}
        old_msg_id = invites.get(str(user.id))
        if old_msg_id:
            try:
                bot.delete_message(chat_id=user.id, message_id=old_msg_id)
            except Exception:
                pass

        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton(
                text="Перейти в групу вакансії",
                url=vacancy.group.invite_link,
            )
        )

        sent = bot.send_message(
            chat_id=user.id,
            text=f"✅ Вас допущено до вакансії як {role_text}.\nПерейдіть у групу за посиланням нижче:",
            reply_markup=markup,
        )

        invites[str(user.id)] = sent.message_id
        if vacancy.extra is None:
            vacancy.extra = {}
        vacancy.extra["apply_invite_msg_ids"] = invites
        vacancy.save(update_fields=["extra"])

        bot.answer_callback_query(call.id, text="Посилання відправлено в бот ✅")
    except Exception:
        sentry_sdk.capture_exception()
        bot.answer_callback_query(call.id, text="Помилка.", show_alert=True)
