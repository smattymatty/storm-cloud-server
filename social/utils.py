"""Utilities for social posting."""
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from storage.models import ShareLink


def format_share_link_post(share_link: "ShareLink") -> str:
    """
    Format a share link announcement for posting to GoToSocial.

    Args:
        share_link: ShareLink instance

    Returns:
        Formatted status text
    """
    # Get base URL for constructing full share link
    base_url = getattr(settings, "STORMCLOUD_BASE_URL", "https://example.com")

    # Get file info
    file_name = share_link.stored_file.name
    file_size = _format_file_size(share_link.stored_file.size)

    # Build share URL
    share_key = share_link.get_public_url_key()
    share_url = f"{base_url}/api/v1/public/{share_key}/"

    # Expiry info
    if share_link.expiry_days == 0:
        expiry = "No expiration"
    else:
        expiry = f"Expires in {share_link.expiry_days} day{'s' if share_link.expiry_days != 1 else ''}"

    # Password protection indicator
    password_note = "🔒 Password protected" if share_link.password_hash else ""

    # Build post
    template = getattr(
        settings,
        "GOTOSOCIAL_SHARE_TEMPLATE",
        "🔗 New file shared: {file_name}\n\n📦 {file_size}\n⏰ {expiry}\n{password_note}\n\n→ {share_url}",
    )

    return template.format(
        file_name=file_name,
        file_size=file_size,
        expiry=expiry,
        password_note=password_note,
        share_url=share_url,
    ).strip()


def _format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    size = float(size_bytes)  # Convert to float for calculations
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"
