from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model

from user.models import AuthIdentity
from api.authentication import validate_telegram_init_data

User = get_user_model()


class TelegramAuthSerializer(serializers.Serializer):
    init_data = serializers.CharField(required=True)

    def validate_init_data(self, value):
        result = validate_telegram_init_data(value, max_age_seconds=86400)
        if result is None:
            raise serializers.ValidationError('Invalid or expired Telegram initData.')
        return result

    def create(self, validated_data):
        tg_user = validated_data['init_data']['user']
        tg_id = tg_user['id']

        # Try to find user via AuthIdentity first
        try:
            identity = AuthIdentity.objects.select_related('user').get(
                provider=AuthIdentity.Provider.TELEGRAM,
                provider_uid=str(tg_id),
            )
            user = identity.user
        except AuthIdentity.DoesNotExist:
            # Fallback: find by telegram_id on User model (backward compat)
            user = User.objects.filter(telegram_id=tg_id).first()
            if user:
                # Create missing AuthIdentity
                AuthIdentity.objects.get_or_create(
                    provider=AuthIdentity.Provider.TELEGRAM,
                    provider_uid=str(tg_id),
                    defaults={'user': user},
                )
            else:
                # New user — will be created on first /start in bot
                # API alone does not create users (bot flow required)
                raise serializers.ValidationError('User not registered. Start the bot first.')

        # Update user info from Telegram
        full_name = f"{tg_user.get('first_name', '')} {tg_user.get('last_name', '')}".strip()
        if full_name and user.full_name != full_name:
            user.full_name = full_name
        tg_username = tg_user.get('username', '')
        if tg_username and user.username != tg_username:
            user.username = tg_username
        user.save(update_fields=['full_name', 'username'])

        # Issue JWT
        refresh = RefreshToken.for_user(user)
        refresh['telegram_id'] = tg_id
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user_id': user.id,
        }
