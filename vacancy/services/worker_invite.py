import logging

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from telegram.handlers.bot_instance import bot

logger = logging.getLogger(__name__)


def send_worker_group_invite(user, vacancy) -> bool:
    """Send group invite link to worker's bot chat. Returns True on success."""
    if not vacancy.group or not vacancy.group.invite_link:
        logger.warning("send_worker_group_invite: no group/invite_link for vacancy %s", vacancy.pk)
        return False

    invites = (vacancy.extra or {}).get("apply_invite_msg_ids", {})
    old_msg_id = invites.get(str(user.id))
    if old_msg_id:
        try:
            bot.delete_message(chat_id=user.id, message_id=old_msg_id)
        except Exception:
            pass

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text="Перейти в групу вакансії", url=vacancy.group.invite_link))

    try:
        sent = bot.send_message(
            chat_id=user.id,
            text="✅ Перейдіть у групу Вашої вакансії для спілкування з замовником.",
            reply_markup=markup,
        )
    except Exception as e:
        logger.warning("send_worker_group_invite: send failed for user %s: %s", user.id, e)
        return False

    if vacancy.extra is None:
        vacancy.extra = {}
    invites[str(user.id)] = sent.message_id
    vacancy.extra["apply_invite_msg_ids"] = invites
    vacancy.save(update_fields=["extra"])

    return True
