import base64
import logging

from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    name = "core"

    def ready(self):
        """Validate encryption settings on startup."""
        from django.conf import settings

        method = getattr(settings, "STORAGE_ENCRYPTION_METHOD", "none")

        if method != "none":
            key = getattr(settings, "STORAGE_ENCRYPTION_KEY", "")

            if not key:
                raise ImproperlyConfigured(
                    "STORAGE_ENCRYPTION_KEY required when STORAGE_ENCRYPTION_METHOD != 'none'. "
                    'Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
                )

            try:
                # Add padding - token_urlsafe() strips it but b64decode needs it
                key_bytes = base64.urlsafe_b64decode(key + "==")
                if len(key_bytes) != 32:
                    raise ValueError("Key must be 32 bytes")
            except Exception as e:
                raise ImproperlyConfigured(
                    f"STORAGE_ENCRYPTION_KEY must be 32 bytes base64-urlsafe encoded. "
                    f'Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))". '
                    f"Error: {e}"
                )

            logger.info(f"Encryption enabled: method={method}")
