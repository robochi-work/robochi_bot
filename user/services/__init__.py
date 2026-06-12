"""Пакет user.services. Реекспорт publicly-used символів зі старого user/services.py."""

from user.services.core import (
    BlockService,
    admin_mark_vacancies_paid,
    find_user_by_phone,
    get_or_create_user_from_telegram,
)

__all__ = [
    "BlockService",
    "admin_mark_vacancies_paid",
    "find_user_by_phone",
    "get_or_create_user_from_telegram",
]
