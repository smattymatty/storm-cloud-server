"""API Key authentication for Storm Cloud."""

from typing import TYPE_CHECKING, Any, Optional, Tuple
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request
from django.contrib.auth import get_user_model
from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension

from .models import APIKey

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser as User
    from .models import Organization
else:
    User = get_user_model()


class APIKeyUser:
    """
    Wrapper class to make org-scoped APIKey work as a user for DRF compatibility.

    When authenticating via API key, this object is set as request.user.
    It provides the necessary attributes for DRF's IsAuthenticated check
    and gives views access to the organization context.
    """
    is_authenticated = True
    is_active = True
    is_anonymous = False

    def __init__(self, api_key: APIKey):
        self.api_key = api_key
        self.organization = api_key.organization
        # For audit logging and compatibility
        self.id = f"apikey:{api_key.id}"
        self.username = f"apikey:{api_key.name}"

        # Inherit admin status from creator (API keys created by admins can do admin things)
        if api_key.created_by and api_key.created_by.user:
            self.is_staff = api_key.created_by.user.is_staff
            self.is_superuser = api_key.created_by.user.is_superuser
        else:
            self.is_staff = False
            self.is_superuser = False

    def __str__(self) -> str:
        return f"APIKey({self.api_key.name})"


    @property
    def pk(self) -> str:
        """Return API key ID as pk for DRF throttling compatibility."""
        return self.api_key.id

    @property
    def account(self):
        """
        Return the account that created this API key for file ownership.

        Files uploaded via API key are owned by the account that created the key.
        """
        return self.api_key.created_by

    def has_perm(self, perm: str, obj: Any = None) -> bool:
        """Check permission via API key's permissions JSON."""
        return self.api_key.has_permission(perm)


class APIKeyAuthentication(BaseAuthentication):
    """
    API key authentication using Bearer token.

    API keys are org-scoped (not user-scoped). When authenticated via API key:
    - request.user is an APIKeyUser wrapper (for DRF compatibility)
    - request.auth is the APIKey instance
    - Views should check request.auth to determine auth method

    Client should authenticate by passing the API key in the Authorization header:
        Authorization: Bearer <api_key>
    """

    keyword = "Bearer"

    def authenticate(self, request: Request) -> Optional[Tuple[APIKeyUser, APIKey]]:
        """
        Authenticate using API key in Authorization header.

        Returns:
            Tuple of (APIKeyUser wrapper, APIKey) if authentication succeeds
            None if Authorization header is not present (allows other authenticators)

        Raises:
            AuthenticationFailed: If API key is invalid, inactive, or org is disabled
        """
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith(f"{self.keyword} "):
            return None

        key = auth_header[len(self.keyword) + 1:]

        try:
            api_key = APIKey.objects.select_related(
                "organization", "created_by", "created_by__user"
            ).get(
                key=key,
                is_active=True,
                revoked_at__isnull=True
            )
        except APIKey.DoesNotExist:
            raise AuthenticationFailed("Invalid API key")

        # Check if organization is active
        if not api_key.organization.is_active:
            raise AuthenticationFailed("Organization is disabled")

        # Update last used timestamp
        api_key.last_used_at = timezone.now()
        api_key.save(update_fields=["last_used_at"])

        # Return APIKeyUser wrapper for DRF compatibility
        return (APIKeyUser(api_key), api_key)


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
