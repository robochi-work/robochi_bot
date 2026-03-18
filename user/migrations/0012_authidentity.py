from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0011_user_telegram_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuthIdentity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider', models.CharField(choices=[('telegram', 'Telegram'), ('phone', 'Phone'), ('email', 'Email'), ('google', 'Google')], max_length=50)),
                ('provider_uid', models.CharField(max_length=255)),
                ('extra_data', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='auth_identities', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Auth Identity',
                'verbose_name_plural': 'Auth Identities',
                'unique_together': {('provider', 'provider_uid')},
            },
        ),
    ]
