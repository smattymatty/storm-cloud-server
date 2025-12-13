"""Utility functions for storage app."""

import uuid
from typing import Optional
from .models import ShareLink


def get_share_link_by_token(token: str) -> Optional[ShareLink]:
    """
    Lookup ShareLink by UUID token or custom slug.

    Args:
        token: Either a UUID string or custom slug

    Returns:
        ShareLink instance if found, None otherwise
    """
    # Try UUID token first
    try:
        uuid.UUID(token)
        return ShareLink.objects.get(token=token)
    except (ValueError, ShareLink.DoesNotExist):
        pass

    # Fall back to custom slug
    try:
        return ShareLink.objects.get(custom_slug=token)
    except ShareLink.DoesNotExist:
        return None
