from django.apps import AppConfig


class StorageConfig(AppConfig):
    name = "storage"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        """Import signal handlers when app is ready."""
        import storage.signal_handlers  # noqa
