from django.apps import AppConfig


class UserConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'user'
    verbose_name = "Користувачі"

    def ready(self):
        import user.admin_site  # noqa: F401
