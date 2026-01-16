"""Utility functions for storage API views."""

from typing import Any

from rest_framework.request import Request

from storage.signals import file_action_performed


def emit_user_file_action(
    sender: Any,
    request: Request,
    action: str,
    path: str,
    success: bool = True,
    **kwargs: Any,
) -> None:
    """Emit file action signal for user operations.

    Creates audit log entry for regular user file operations.
    For admin operations, use emit_admin_file_action() in admin_api.py.
    """
    file_action_performed.send(
        sender=sender,
        performed_by=request.user,
        target_user=request.user,  # User is acting on their own files
        is_admin_action=False,
        action=action,
        path=path,
        success=success,
        request=request,
        **kwargs,
    )
