"""Django signals for accounts app authentication events."""

from django.dispatch import Signal


# Fired when a new user registers
user_registered = Signal()  # sender=User, user=user_instance, request=request

# Fired when email is verified
email_verified = Signal()  # sender=User, user=user_instance

# Fired when API key is created
api_key_created = Signal()  # sender=APIKey, api_key=key_instance, user=user

# Fired when API key is revoked
api_key_revoked = (
    Signal()
)  # sender=APIKey, api_key=key_instance, user=user, revoked_by=user

# Fired when account is deactivated
account_deactivated = Signal()  # sender=User, user=user_instance

# Fired when account is deleted
account_deleted = Signal()  # sender=User, user_id=id, username=username

# Fired on failed login attempt
login_failed = Signal()  # sender=None, username=username, ip_address=ip, reason=reason
