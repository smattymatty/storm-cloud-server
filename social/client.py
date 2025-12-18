"""GoToSocial API client for posting statuses."""
import logging
from typing import Any, Dict, Optional

import requests
from django.conf import settings

from .exceptions import GoToSocialError

logger = logging.getLogger(__name__)


class GoToSocialClient:
    """Client for interacting with GoToSocial API."""

    def __init__(self, domain: str, token: str):
        self.domain = domain
        self.token = token
        self.base_url = f"https://{domain}"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )

    @classmethod
    def from_settings(cls) -> Optional["GoToSocialClient"]:
        """Create client from Django settings."""
        domain = getattr(settings, "GOTOSOCIAL_DOMAIN", None)
        token = getattr(settings, "GOTOSOCIAL_TOKEN", None)

        if not domain or not token:
            logger.warning(
                "GoToSocial not configured (missing GOTOSOCIAL_DOMAIN or GOTOSOCIAL_TOKEN)"
            )
            return None

        return cls(domain=domain, token=token)

    def post_status(
        self,
        status: str,
        visibility: str = "public",
        sensitive: bool = False,
        spoiler_text: str = "",
    ) -> Dict[str, Any]:
        """
        Post a status to GoToSocial.

        Args:
            status: The text content of the status
            visibility: "public", "unlisted", "private", or "direct"
            sensitive: Mark as sensitive content
            spoiler_text: Content warning text

        Returns:
            Dict with 'id', 'url', 'created_at', etc.

        Raises:
            GoToSocialError: If posting fails
        """
        endpoint = f"{self.base_url}/api/v1/statuses"

        payload = {
            "status": status,
            "visibility": visibility,
            "sensitive": sensitive,
        }

        if spoiler_text:
            payload["spoiler_text"] = spoiler_text

        try:
            response = self.session.post(endpoint, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Validate response is a dict (GoToSocial should always return dict)
            if not isinstance(data, dict):
                raise GoToSocialError(
                    f"Expected dict response from GoToSocial, got {type(data).__name__}"
                )
            
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to post status to GoToSocial: {e}")
            raise GoToSocialError(f"Failed to post status: {e}") from e

    def delete_status(self, status_id: str) -> bool:
        """
        Delete a status from GoToSocial.

        Args:
            status_id: The ID of the status to delete

        Returns:
            True if successful, False otherwise
        """
        endpoint = f"{self.base_url}/api/v1/statuses/{status_id}"

        try:
            response = self.session.delete(endpoint, timeout=10)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to delete status {status_id}: {e}")
            return False

    def verify_credentials(self) -> Dict[str, Any]:
        """Verify API credentials and get account info."""
        endpoint = f"{self.base_url}/api/v1/accounts/verify_credentials"

        try:
            response = self.session.get(endpoint, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Validate response is a dict
            if not isinstance(data, dict):
                raise GoToSocialError(
                    f"Expected dict response from GoToSocial, got {type(data).__name__}"
                )
            
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to verify GoToSocial credentials: {e}")
            raise GoToSocialError(f"Failed to verify credentials: {e}") from e
