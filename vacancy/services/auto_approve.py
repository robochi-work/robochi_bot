import logging

from telegram.service.group import GroupService
from vacancy.choices import STATUS_APPROVED

logger = logging.getLogger(__name__)


def try_auto_approve(vacancy) -> bool:
    """
    Check if owner has auto_approve_vacancy enabled.
    If yes: assign channel + group, set status approved.
    Returns True if auto-approved, False otherwise.
    """
    work_profile = getattr(vacancy.owner, "work_profile", None)
    if not work_profile or not work_profile.auto_approve_vacancy:
        return False

    # Ensure channel is set
    if not vacancy.channel:
        from telegram.models import Channel

        try:
            vacancy.channel = Channel.objects.get(city=work_profile.city)
        except Exception:
            logger.warning("Auto-approve: no channel for city %s", work_profile.city)
            return False

    # Assign group if not already set
    if not vacancy.group:
        from telegram.choices import STATUS_PROCESS

        group = GroupService.get_available_group()
        if not group:
            logger.warning("Auto-approve: no available group for vacancy %s", vacancy.pk)
            _notify_admins_no_group(vacancy)
            return False
        vacancy.group = group
        group.status = STATUS_PROCESS
        group.save(update_fields=["status"])

    vacancy.status = STATUS_APPROVED
    vacancy.search_active = True
    vacancy.extra["auto_approved"] = True
    vacancy.save()

    # Notify admins with auto-approved mark
    _notify_admins_auto_approved(vacancy)

    return True


def _notify_admins_auto_approved(vacancy):
    """Send admin notification with auto-approved mark."""
    from telegram.handlers.bot_instance import bot
    from user.models import User
    from vacancy.services.vacancy_formatter import VacancyTelegramTextFormatter

    text = "✅ Автоматично підтверджено\n\n" + VacancyTelegramTextFormatter(vacancy).for_admin_chat()
    admin_ids = list(User.objects.filter(is_staff=True).values_list("id", flat=True))

    for admin_id in admin_ids:
        try:
            bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception:
            logger.exception("Failed to send auto-approve msg to admin %s", admin_id)


def _notify_admins_no_group(vacancy):
    """Notify admins that auto-approve failed due to no available groups."""
    from telegram.handlers.bot_instance import bot
    from user.models import User

    owner_name = vacancy.owner.full_name or vacancy.owner.username
    text = (
        f"⚠️ Немає вільних груп!\n\n"
        f"Вакансія: {vacancy.address}\n"
        f"Замовник: {owner_name}\n\n"
        f"Автопідтвердження не спрацювало — вакансія очікує модерації."
    )
    admin_ids = list(User.objects.filter(is_staff=True).values_list("id", flat=True))

    for admin_id in admin_ids:
        try:
            bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception:
            logger.exception("Failed to send no-group msg to admin %s", admin_id)
