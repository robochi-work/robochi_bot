from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vacancy', '0024_add_contact_phone'),
    ]

    operations = [
        migrations.AddField(
            model_name='vacancy',
            name='search_active',
            field=models.BooleanField(default=False, verbose_name='Search active (button visible)'),
        ),
    ]
