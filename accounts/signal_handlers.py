"""Signal handlers for security logging."""

import logging
from django.dispatch import receiver
from .signals import (
    user_registered,
    email_verified,
    api_key_created,
    api_key_revoked,
    account_deactivated,
    account_deleted,
    login_failed
)
from .utils import get_client_ip


security_logger = logging.getLogger('stormcloud.security')


@receiver(user_registered)
def log_user_registered(sender, user, request, **kwargs):
    ip = get_client_ip(request)
    security_logger.info(
        f"USER_REGISTERED user_id={user.id} username={user.username} "
        f"email={user.email} ip={ip}"
    )


@receiver(email_verified)
def log_email_verified(sender, user, **kwargs):
    security_logger.info(
        f"EMAIL_VERIFIED user_id={user.id} username={user.username}"
    )


@receiver(api_key_created)
def log_api_key_created(sender, api_key, user, **kwargs):
    # Handle both real User and APIKeyUser, and None
    user_id = getattr(user, 'id', None) if user else None
    security_logger.info(
        f"API_KEY_CREATED user_id={user_id} key_id={api_key.id} "
        f"key_name={api_key.name}"
    )


@receiver(api_key_revoked)
def log_api_key_revoked(sender, api_key, user, revoked_by, **kwargs):
    # Handle both real User and APIKeyUser, and None
    user_id = getattr(user, 'id', None) if user else None
    revoked_by_id = getattr(revoked_by, 'id', None) if revoked_by else None
    security_logger.info(
        f"API_KEY_REVOKED user_id={user_id} key_id={api_key.id} "
        f"key_name={api_key.name} revoked_by={revoked_by_id}"
    )


@receiver(account_deactivated)
def log_account_deactivated(sender, user, **kwargs):
    security_logger.warning(
        f"ACCOUNT_DEACTIVATED user_id={user.id} username={user.username}"
    )


@receiver(account_deleted)
def log_account_deleted(sender, user_id, username, **kwargs):
    security_logger.warning(
        f"ACCOUNT_DELETED user_id={user_id} username={username}"
    )


@receiver(login_failed)
def log_login_failed(sender, username, ip_address, reason, **kwargs):
    security_logger.warning(
        f"LOGIN_FAILED username={username} ip={ip_address} reason={reason}"
    )
