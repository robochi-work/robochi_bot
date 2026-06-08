import base64
import json
import logging
from datetime import timedelta

import sentry_sdk
from django.utils import timezone
from telebot.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from telegram.handlers.bot_instance import bot
from telegram.models import Status
from user.models import User
from user.services import BlockService
from vacancy.choices import GENDER_ANY, STATUS_APPROVED
from vacancy.models import Vacancy, VacancyUser
from vacancy.services.call_formatter import CallVacancyTelegramTextFormatter

logger = logging.getLogger(__name__)


def _encode_start_payload(data: dict) -> str:
    json_str = json.dumps(data, separators=(",", ":"))
    return base64.urlsafe_b64encode(json_str.encode()).decode().rstrip("=")


@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("apply:"))
def handle_apply_vacancy(call: CallbackQuery):
    try:
        vacancy_id = int(call.data.split(":")[1])
    except (IndexError, ValueError):
        bot.answer_callback_query(call.id, text="Помилка. Спробуйте ще раз.", show_alert=True)
        return

    try:
        user, _ = User.objects.update_or_create(id=call.from_user.id, defaults={"username": call.from_user.username})

        work_profile = getattr(user, "work_profile", None)

        # 1. Admin — перенаправление в бот через deep link
        if user.is_staff:
            payload = _encode_start_payload({"type": "admin_apply", "vacancy_id": vacancy_id})
            deep_link = f"https://t.me/riznorobochi_ua_bot?start={payload}"
            try:
                bot.answer_callback_query(call.id, url=deep_link)
            except Exception:
                bot.answer_callback_query(call.id, text="Перейдіть у бота для продовження.", show_alert=True)
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
            bot.answer_callback_query(
                call.id,
                text="Спочатку зареєструйтеся у нашому сервісі:\n@riznorobochi_ua_bot\n\nАбо зверніться до Адміністратора:\n@robochi_work_admin",
                show_alert=True,
            )
            return

        # 5.5 Rate limit: max 2 voluntary exits per hour
        from user.models import WorkerVoluntaryExit

        one_hour_ago = timezone.now() - timedelta(hours=1)
        exit_count = WorkerVoluntaryExit.objects.filter(
            user=user,
            created_at__gte=one_hour_ago,
        ).count()
        if exit_count >= 2:
            # Create auto-dislike only once per rate-limit window
            from user.models import UserFeedback

            already_penalized = UserFeedback.objects.filter(
                user=user,
                is_auto=True,
                extra__reason="excessive_exits",
                created_at__gte=one_hour_ago,
            ).exists()
            if not already_penalized:
                UserFeedback.objects.create(
                    owner=user,
                    user=user,
                    rating="dislike",
                    is_auto=True,
                    text="",
                    extra={"reason": "excessive_exits"},
                )
                logger.info("rate_limit_dislike", extra={"user_id": user.id, "exit_count": exit_count})
            bot.answer_callback_query(
                call.id,
                show_alert=True,
                text="Багато спроб обрати вакансію! Спробуйте через годину!",
            )
            logger.warning("apply_rate_limited", extra={"user_id": user.id, "exit_count": exit_count})
            return

        # 6. Получаем вакансию
        try:
            vacancy = Vacancy.objects.select_related("group", "owner").get(id=vacancy_id, status=STATUS_APPROVED)
        except Vacancy.DoesNotExist:
            bot.answer_callback_query(call.id, show_alert=True, text="Вакансію не знайдено або вона вже закрита.")
            return

        # 7. Owner вакансии — автоперехід в бот через deep link
        if vacancy.owner == user:
            from django.core.cache import cache

            throttle_key = f"apply_throttle:{user.id}:{vacancy_id}"
            if cache.get(throttle_key):
                bot.answer_callback_query(call.id, text="Зачекайте трохи")
                return
            cache.set(throttle_key, True, timeout=300)
            payload = _encode_start_payload({"type": "apply", "vacancy_id": vacancy_id})
            deep_link = f"https://t.me/riznorobochi_ua_bot?start={payload}"
            try:
                bot.answer_callback_query(call.id, url=deep_link)
            except Exception:
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
                user=user, status__in=[Status.MEMBER, Status.PENDING_CONFIRM], vacancy__status=STATUS_APPROVED
            )
            .exclude(vacancy=vacancy)
            .exists()
        ):
            bot.answer_callback_query(
                call.id, show_alert=True, text="Ви вже берете участь в іншій вакансії. Спочатку завершіть поточну."
            )
            return

        # 9b. Уже в ЭТОЙ вакансии — redirect to cabinet
        if VacancyUser.objects.filter(
            user=user, vacancy=vacancy, status__in=[Status.MEMBER, Status.PENDING_CONFIRM]
        ).exists():
            from django.core.cache import cache

            throttle_key = f"apply_throttle:{user.id}:{vacancy_id}"
            if cache.get(throttle_key):
                bot.answer_callback_query(call.id, text="Зачекайте трохи")
                return
            cache.set(throttle_key, True, timeout=300)
            payload = _encode_start_payload({"type": "already_in_vacancy", "vacancy_id": vacancy_id})
            deep_link = f"https://t.me/riznorobochi_ua_bot?start={payload}"
            try:
                bot.answer_callback_query(call.id, url=deep_link)
            except Exception:
                bot.answer_callback_query(call.id, text="Перейдіть у бота для продовження.", show_alert=True)
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

        # Все проверки пройдены — автоперехід в бот через deep link
        payload = _encode_start_payload({"type": "apply", "vacancy_id": vacancy_id})
        deep_link = f"https://t.me/riznorobochi_ua_bot?start={payload}"
        try:
            bot.answer_callback_query(call.id, url=deep_link)
        except Exception:
            bot.answer_callback_query(call.id, text="Перейдіть у бота для продовження.", show_alert=True)
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
        markup.add(InlineKeyboardButton(text="Перейти в групу вакансії", url=vacancy.group.invite_link))

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
