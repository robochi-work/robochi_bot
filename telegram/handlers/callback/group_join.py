import json
import logging

from telebot.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from telegram.handlers.bot_instance import bot
from user.models import User
from vacancy.choices import STATUS_ACTIVE, STATUS_APPROVED
from vacancy.models import Vacancy

logger = logging.getLogger(__name__)


@bot.callback_query_handler(func=lambda c: c.data and '"t": "group_join"' in c.data)
def handle_group_join(callback: CallbackQuery) -> None:
    """Check vacancy limit before sending group invite link."""
    try:
        data = json.loads(callback.data)
    except (json.JSONDecodeError, TypeError):
        return

    if data.get("t") != "group_join":
        return

    user = User.objects.filter(id=callback.from_user.id).first()
    if not user:
        return

    vacancy = (
        Vacancy.objects.filter(
            id=data.get("v"),
            status__in=[STATUS_APPROVED, STATUS_ACTIVE],
        )
        .select_related("group")
        .first()
    )

    if not vacancy or not vacancy.group or not vacancy.group.invite_link:
        bot.answer_callback_query(callback.id, text="Вакансію не знайдено.", show_alert=True)
        return

    # Check group limit
    if vacancy.members.count() >= vacancy.people_count:
        bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
        bot.send_message(
            chat_id=callback.message.chat.id,
            text="Упс, схоже ця вакансія вже зайнята! Натискайте Перейти та обирайте інші вакансії!",
        )
        # Mark user as LEFT since vacancy is full
        from telegram.choices import Status
        from vacancy.models import VacancyUser

        VacancyUser.objects.filter(user=user, vacancy=vacancy).update(status=Status.LEFT)
        bot.answer_callback_query(callback.id)
        return

    # All OK — send invite link via answer_callback_query(url=)
    try:
        bot.answer_callback_query(callback.id, url=vacancy.group.invite_link)
    except Exception:
        # Fallback: send link as message
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(text="Перейти в групу", url=vacancy.group.invite_link))
        bot.send_message(
            chat_id=callback.message.chat.id,
            text="Перейдіть у групу:",
            reply_markup=markup,
        )
        bot.answer_callback_query(callback.id)
    logger.info(f"group_join: user {user.id} joining vacancy {vacancy.id}")
