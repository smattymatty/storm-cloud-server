"""Permission checking utilities for Storm Cloud."""

from typing import TYPE_CHECKING

from rest_framework.exceptions import PermissionDenied

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser


def check_user_permission(user: "AbstractBaseUser", permission_name: str) -> None:
    """
    Check if user has a specific permission flag enabled.

    Args:
        user: The authenticated user
        permission_name: Name of the permission field on UserProfile
            (e.g., 'can_upload', 'can_delete', 'can_move', 'can_overwrite', 'can_create_shares')

    Raises:
        PermissionDenied: If the user doesn't have the permission
    """
    profile = user.profile
    if not getattr(profile, permission_name, True):
        raise PermissionDenied(
            detail={
                "error": {
                    "code": "PERMISSION_DENIED",
                    "message": f"You do not have permission to perform this action.",
                    "permission": permission_name,
                }
            }
        )


def check_max_upload_size(user: "AbstractBaseUser", file_size: int) -> None:
    """
    Check if file size exceeds user's per-file upload limit.

    Args:
        user: The authenticated user
        file_size: Size of the file being uploaded in bytes

    Raises:
        PermissionDenied: If file exceeds user's max_upload_bytes limit
    """
    profile = user.profile
    max_bytes = profile.max_upload_bytes

    # 0 = use server default (no per-user limit)
    if max_bytes == 0:
        return

    if file_size > max_bytes:
        raise PermissionDenied(
            detail={
                "error": {
                    "code": "FILE_TOO_LARGE",
                    "message": f"File size exceeds your per-file limit of {max_bytes} bytes.",
                    "limit_bytes": max_bytes,
                }
            }
        )


def check_share_link_limit(user: "AbstractBaseUser") -> None:
    """
    Check if user can create another share link.

    Args:
        user: The authenticated user

    Raises:
        PermissionDenied: If user has reached max_share_links limit
    """
    from storage.models import ShareLink

    profile = user.profile
    max_links = profile.max_share_links

    # 0 = unlimited
    if max_links == 0:
        return

    current_count = ShareLink.objects.filter(
        owner=user,
        is_active=True
    ).count()

    if current_count >= max_links:
        raise PermissionDenied(
            detail={
                "error": {
                    "code": "MAX_SHARE_LINKS_EXCEEDED",
                    "message": f"Maximum of {max_links} active share links allowed.",
                    "limit": max_links,
                    "current": current_count,
                }
            }
        )
