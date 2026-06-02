"""Unified formatting for admin service messages.

All admin notifications use these helpers to ensure consistent
user-data blocks and group links across the entire project.
"""

from vacancy.models import Vacancy


def format_user_block(user) -> str:
    """Standard user data block for service messages.

    ID: 123456789
    Ім'я: Петро Іваненко
    Username: @petro_iv
    Телефон: +380501234567
    """
    username = f"@{user.username}" if user.username else "—"
    phone = user.phone_number or "—"
    return (
        f"<b>ID:</b> <code>{user.pk}</code>\n"
        f"<b>Ім'я:</b> {user.full_name or '—'}\n"
        f"<b>Username:</b> {username}\n"
        f"<b>Телефон:</b> {phone}"
    )


def format_user_block_with_contact(user, vacancy: Vacancy) -> str:
    """User data block with both registration and vacancy contact phones.

    ID: 123456789
    Ім'я: Петро Іваненко
    Username: @petro_iv
    Телефон: +380501234567
    Контактний: +380991114455
    """
    from vacancy.models import VacancyContactPhone

    block = format_user_block(user)
    cp = VacancyContactPhone.objects.filter(vacancy=vacancy, user=user).first()
    if cp and cp.phone and cp.phone != (user.phone_number or ""):
        block += f"\n<b>Контактний:</b> {cp.phone}"
    return block


def format_group_link(vacancy: Vacancy) -> str:
    """Group invite link line. Returns empty string if no group/link."""
    if vacancy.group and vacancy.group.invite_link:
        return f"\n<b>Група:</b> {vacancy.group.invite_link}"
    return ""
