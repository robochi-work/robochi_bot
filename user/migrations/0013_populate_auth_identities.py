from django.db import migrations


def populate_auth_identities(apps, schema_editor):
    User = apps.get_model('user', 'User')
    AuthIdentity = apps.get_model('user', 'AuthIdentity')

    for user in User.objects.all():
        # Telegram identity
        tg_id = user.telegram_id or user.id
        if tg_id:
            AuthIdentity.objects.get_or_create(
                provider='telegram',
                provider_uid=str(tg_id),
                defaults={'user': user}
            )
        # Phone identity
        if user.phone_number:
            AuthIdentity.objects.get_or_create(
                provider='phone',
                provider_uid=user.phone_number,
                defaults={'user': user}
            )


def reverse_populate(apps, schema_editor):
    AuthIdentity = apps.get_model('user', 'AuthIdentity')
    AuthIdentity.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ('user', '0012_authidentity'),
    ]
    operations = [
        migrations.RunPython(populate_auth_identities, reverse_populate),
    ]
