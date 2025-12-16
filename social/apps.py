"""Social app configuration."""
from django.apps import AppConfig


class SocialConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "social"
    verbose_name = "Social Integration"

    def ready(self):
        """Import signal handlers when app is ready."""
        import social.signals  # noqa
