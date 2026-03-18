from django.db import transaction
from django.contrib.auth import get_user_model

from user.models import AuthIdentity

User = get_user_model()


def get_or_create_user_from_telegram(
    *, telegram_id: int, full_name: str = '', username: str = '', phone_number: str = ''
) -> tuple:
    """
    Находит или создаёт пользователя по Telegram ID.
    Обновляет full_name и username при каждом входе.
    Возвращает (user, created).
    """
    with transaction.atomic():
        user, created = User.objects.get_or_create(
            id=telegram_id,
            defaults={
                'telegram_id': telegram_id,
                'full_name': full_name,
                'username': username or f'tg_{telegram_id}',
                'phone_number': phone_number,
            }
        )
        if not created:
            update_fields = []
            if full_name and user.full_name != full_name:
                user.full_name = full_name
                update_fields.append('full_name')
            if username and user.username != username:
                user.username = username
                update_fields.append('username')
            if update_fields:
                user.save(update_fields=update_fields)

        # Ensure AuthIdentity exists
        AuthIdentity.objects.get_or_create(
            provider=AuthIdentity.Provider.TELEGRAM,
            provider_uid=str(telegram_id),
            defaults={'user': user},
        )
        if phone_number:
            AuthIdentity.objects.get_or_create(
                provider=AuthIdentity.Provider.PHONE,
                provider_uid=phone_number,
                defaults={'user': user},
            )

    return user, created


def find_user_by_phone(*, phone_number: str):
    """Поиск пользователя по номеру телефона через AuthIdentity."""
    try:
        identity = AuthIdentity.objects.select_related('user').get(
            provider=AuthIdentity.Provider.PHONE,
            provider_uid=phone_number,
        )
        return identity.user
    except AuthIdentity.DoesNotExist:
        return None
