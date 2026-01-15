"""Permission checking utilities for Storm Cloud."""

from typing import TYPE_CHECKING, Union

from rest_framework.exceptions import PermissionDenied

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser
    from accounts.models import Account, APIKey


def get_permission_source(request) -> Union["Account", "APIKey"]:
    """
    Get the permission source for the current request.

    For session auth, returns the user's Account.
    For API key auth, returns the APIKey (which has its own permissions).

    Args:
        request: The DRF request object

    Returns:
        Account or APIKey depending on authentication method

    Raises:
        PermissionDenied: If no valid permission source found
    """
    from accounts.models import APIKey

    # Check if authenticated via API key
    if hasattr(request, 'auth') and isinstance(request.auth, APIKey):
        return request.auth

    # Session auth - return user's account
    if hasattr(request, 'user') and hasattr(request.user, 'account'):
        return request.user.account

    raise PermissionDenied(
        detail={
            "error": {
                "code": "NOT_AUTHENTICATED",
                "message": "Authentication required.",
            }
        }
    )


def check_permission(source: Union["Account", "APIKey"], permission_name: str) -> None:
    """
    Check if the permission source (Account or APIKey) has a specific permission.

    For Account: checks the boolean field directly
    For APIKey: checks the permissions JSON (defaults to True if not set)

    Args:
        source: Account or APIKey instance
        permission_name: Name of the permission (e.g., 'can_upload', 'can_delete')

    Raises:
        PermissionDenied: If permission is denied
    """
    from accounts.models import APIKey

    if isinstance(source, APIKey):
        # API keys use permissions JSON, default to True
        has_permission = source.has_permission(permission_name)
    else:
        # Account uses boolean fields - fail if permission doesn't exist
        if not hasattr(source, permission_name):
            raise ValueError(f"Unknown permission: {permission_name}")
        has_permission = getattr(source, permission_name)

    if not has_permission:
        raise PermissionDenied(
            detail={
                "error": {
                    "code": "PERMISSION_DENIED",
                    "message": "You do not have permission to perform this action.",
                    "permission": permission_name,
                }
            }
        )


def check_user_permission(user: "AbstractBaseUser", permission_name: str) -> None:
    """
    Check if user has a specific permission flag enabled.

    Args:
        user: The authenticated user (or APIKeyUser)
        permission_name: Name of the permission field on Account
            (e.g., 'can_upload', 'can_delete', 'can_move', 'can_overwrite', 'can_create_shares')

    Raises:
        PermissionDenied: If the user doesn't have the permission
    """
    from accounts.authentication import APIKeyUser

    if isinstance(user, APIKeyUser):
        # Check API key's own permissions
        if not user.api_key.has_permission(permission_name):
            raise PermissionDenied(
                detail={
                    "error": {
                        "code": "PERMISSION_DENIED",
                        "message": "You do not have permission to perform this action.",
                        "permission": permission_name,
                    }
                }
            )
        # Also check the creating account's permissions
        account = user.api_key.created_by
        if account:
            if not hasattr(account, permission_name):
                raise ValueError(f"Unknown permission: {permission_name}")
            if not getattr(account, permission_name):
                raise PermissionDenied(
                    detail={
                        "error": {
                            "code": "PERMISSION_DENIED",
                            "message": "You do not have permission to perform this action.",
                            "permission": permission_name,
                        }
                    }
                )
        return

    # Session auth - use account
    account = user.account
    if not hasattr(account, permission_name):
        raise ValueError(f"Unknown permission: {permission_name}")
    if not getattr(account, permission_name):
        raise PermissionDenied(
            detail={
                "error": {
                    "code": "PERMISSION_DENIED",
                    "message": "You do not have permission to perform this action.",
                    "permission": permission_name,
                }
            }
        )


def check_max_upload_size(user: "AbstractBaseUser", file_size: int) -> None:
    """
    Check if file size exceeds user's per-file upload limit.

    Args:
        user: The authenticated user (or APIKeyUser)
        file_size: Size of the file being uploaded in bytes

    Raises:
        PermissionDenied: If file exceeds user's max_upload_bytes limit
    """
    from accounts.authentication import APIKeyUser

    if isinstance(user, APIKeyUser):
        # API keys don't have per-user upload limits, use server default
        return

    account = user.account
    max_bytes = account.max_upload_bytes

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
        user: The authenticated user (or APIKeyUser)

    Raises:
        PermissionDenied: If user has reached max_share_links limit
    """
    from accounts.authentication import APIKeyUser
    from storage.models import ShareLink

    if isinstance(user, APIKeyUser):
        # Check the creating account's share link limit
        account = user.api_key.created_by
        if not account:
            return  # No account, no limit to check
    else:
        account = user.account

    max_links = account.max_share_links

    # 0 = unlimited
    if max_links == 0:
        return

    current_count = ShareLink.objects.filter(
        owner=account,
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


# ============================================================================
# DRF Permission Classes for new org admin permissions
# ============================================================================

from rest_framework.permissions import BasePermission


class IsAccountActive(BasePermission):
    """Check that the user has an active account."""

    def has_permission(self, request, view) -> bool:
        if not request.user.is_authenticated:
            return False
        account = getattr(request.user, 'account', None)
        if not account:
            return False
        return account.is_active and account.organization.is_active


class CanInvite(IsAccountActive):
    """Check that the user can create enrollment keys."""

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        return request.user.account.can_invite


class CanManageMembers(IsAccountActive):
    """Check that the user can manage org members."""

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        return request.user.account.can_manage_members


class CanManageAPIKeys(IsAccountActive):
    """Check that the user can manage org API keys."""

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        return request.user.account.can_manage_api_keys


class IsOrgOwner(IsAccountActive):
    """Check that the user is an org owner."""

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        return request.user.account.is_owner
