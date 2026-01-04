"""Signal handlers for file audit logging."""

import logging
from typing import Any, Optional

from django.contrib.auth import get_user_model
from django.dispatch import receiver

from accounts.utils import get_client_ip

from .models import FileAuditLog
from .signals import file_action_performed

User = get_user_model()

# Separate audit logger for file operations
audit_logger = logging.getLogger("stormcloud.audit")


@receiver(file_action_performed)
def log_file_action(
    sender: Any,
    performed_by: Optional[User],
    target_user: Optional[User],
    is_admin_action: bool,
    action: str,
    path: str,
    success: bool,
    request: Any,
    **kwargs: Any,
) -> None:
    """
    Create audit log entry for file action.

    This handler:
    1. Creates a FileAuditLog database record for queryable audit trail
    2. Logs to file logger for external monitoring/SIEM integration
    """
    # Extract request metadata
    ip_address = get_client_ip(request) if request else None
    user_agent = (
        request.headers.get("User-Agent", "")[:500]
        if request and hasattr(request, "headers")
        else None
    )

    # Create audit log entry in database
    FileAuditLog.objects.create(
        performed_by=performed_by,
        target_user=target_user,
        is_admin_action=is_admin_action,
        action=action,
        path=path,
        success=success,
        destination_path=kwargs.get("destination_path"),
        paths_affected=kwargs.get("paths_affected"),
        error_code=kwargs.get("error_code"),
        error_message=kwargs.get("error_message"),
        ip_address=ip_address,
        user_agent=user_agent,
        file_size=kwargs.get("file_size"),
        content_type=kwargs.get("content_type"),
    )

    # Also log to file for external monitoring
    admin_marker = "[ADMIN] " if is_admin_action else ""
    status = "SUCCESS" if success else f"FAILED ({kwargs.get('error_code', 'UNKNOWN')})"
    performer_id = performed_by.id if performed_by else "N/A"
    target_id = target_user.id if target_user else "N/A"

    audit_logger.info(
        f"{admin_marker}FILE_{action.upper()} "
        f"performed_by={performer_id} "
        f"target_user={target_id} "
        f"path={path} "
        f"status={status} "
        f"ip={ip_address}"
    )
