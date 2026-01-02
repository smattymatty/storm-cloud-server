"""Utility functions for storage app."""

import uuid
from datetime import datetime
from hashlib import md5
from typing import Optional

from .models import ShareLink


def generate_etag(path: str, size: int, modified_at: datetime) -> str:
    """
    Generate ETag from file metadata.

    Uses path + size + modified_at to detect changes without reading file content.
    This allows conditional GET requests (If-None-Match) to skip file I/O when
    the client's cached version is still valid.

    Args:
        path: File path (user-relative)
        size: File size in bytes
        modified_at: Last modification timestamp

    Returns:
        MD5 hash string suitable for use as an ETag value
    """
    composite = f"{path}:{size}:{modified_at.isoformat()}"
    return md5(composite.encode()).hexdigest()


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
