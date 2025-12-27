"""API Key authentication for Storm Cloud."""

from typing import TYPE_CHECKING, Any
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request
from django.contrib.auth import get_user_model
from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension

from .models import APIKey

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser as User
else:
    User = get_user_model()


class APIKeyAuthentication(BaseAuthentication):
    """
    API key authentication using Bearer token.

    Client should authenticate by passing the API key in the Authorization header:
        Authorization: Bearer <api_key>
    """

    keyword = "Bearer"

    def authenticate(self, request: Request) -> tuple[User, APIKey] | None:
        """
        Authenticate using API key in Authorization header.

        Returns:
            Tuple of (user, api_key) if authentication succeeds
            None if Authorization header is not present (allows other authenticators)

        Raises:
            AuthenticationFailed: If API key is invalid or inactive
        """
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith(f"{self.keyword} "):
            return None

        key = auth_header[len(self.keyword) + 1 :]

        try:
            api_key = APIKey.objects.select_related("user").get(key=key, is_active=True)
        except APIKey.DoesNotExist:
            raise AuthenticationFailed("Invalid API key")

        # Update last used timestamp
        api_key.last_used_at = timezone.now()
        api_key.save(update_fields=["last_used_at"])

        return (api_key.user, api_key)


class APIKeyAuthenticationScheme(OpenApiAuthenticationExtension):
    """OpenAPI schema extension for API Key authentication."""

    target_class = "accounts.authentication.APIKeyAuthentication"
    name = "APIKeyAuth"

    def get_security_definition(self, auto_schema: Any) -> dict[str, str]:
        """Define the security scheme for OpenAPI."""
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "API Key",
            "description": "API key authentication using Bearer token. Format: `Authorization: Bearer <api_key>`",
        }
