from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from core.models import AbstractBaseModel
import secrets


def generate_verification_token() -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(48)


class UserProfile(AbstractBaseModel):
    """Extended user profile for Storm Cloud specific fields."""

    user = models.OneToOneField(
        get_user_model(),
        on_delete=models.CASCADE,
        related_name='profile'
    )
    is_email_verified = models.BooleanField(default=False)

    # Storage quota (Task 003)
    storage_quota_bytes = models.BigIntegerField(
        default=0,
        help_text="Maximum storage allowed in bytes. 0 = unlimited."
    )
    storage_used_bytes = models.BigIntegerField(
        default=0,
        help_text="Current storage usage in bytes."
    )

    # Permission flags - granular control over user capabilities
    can_upload = models.BooleanField(
        default=True,
        help_text="User can upload new files."
    )
    can_delete = models.BooleanField(
        default=True,
        help_text="User can delete files and folders."
    )
    can_move = models.BooleanField(
        default=True,
        help_text="User can move/rename files and folders."
    )
    can_overwrite = models.BooleanField(
        default=True,
        help_text="User can overwrite/edit existing files."
    )
    can_create_shares = models.BooleanField(
        default=True,
        help_text="User can create share links."
    )
    max_share_links = models.PositiveIntegerField(
        default=0,
        help_text="Maximum active share links allowed. 0 = unlimited."
    )
    max_upload_bytes = models.BigIntegerField(
        default=0,
        help_text="Per-file upload size limit in bytes. 0 = use server default."
    )

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"Profile: {self.user.username}"

    @property
    def storage_remaining_bytes(self) -> int:
        """
        Bytes remaining in quota.

        Returns:
            Remaining bytes, or -1 if unlimited
        """
        if self.storage_quota_bytes == 0:
            return -1
        return max(0, self.storage_quota_bytes - self.storage_used_bytes)

    @property
    def is_over_quota(self) -> bool:
        """Check if user has exceeded storage quota."""
        if self.storage_quota_bytes == 0:
            return False
        return self.storage_used_bytes >= self.storage_quota_bytes

    def update_storage_usage(self, delta_bytes: int) -> None:
        """
        Update storage usage by delta (positive or negative).

        Args:
            delta_bytes: Change in storage usage (positive for increase, negative for decrease)
        """
        self.storage_used_bytes = max(0, self.storage_used_bytes + delta_bytes)
        self.save(update_fields=['storage_used_bytes', 'updated_at'])


class EmailVerificationToken(AbstractBaseModel):
    """Token for email verification flow."""

    user = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        related_name='verification_tokens'
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_verification_token
    )
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Email Verification Token"
        verbose_name_plural = "Email Verification Tokens"
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['user', 'used_at']),
        ]

    def __str__(self):
        status = "used" if self.used_at else "pending"
        return f"Token for {self.user.username} ({status})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.is_expired and self.used_at is None

    def mark_used(self) -> None:
        self.used_at = timezone.now()
        self.save(update_fields=['used_at'])


class APIKey(AbstractBaseModel):
    """API key for CLI/programmatic access."""

    user = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        related_name='api_keys'
    )
    name = models.CharField(max_length=100)  # e.g., "CLI key", "CI/CD key"
    key = models.CharField(max_length=64, unique=True, editable=False)
    last_used_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    # New fields for Task 002
    scope = models.JSONField(
        default=list,
        blank=True,
        help_text="Reserved for future use. List of permission scopes."
    )
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when key was revoked. Set alongside is_active=False."
    )

    class Meta:
        verbose_name = "API Key"
        verbose_name_plural = "API Keys"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        """Generate key on first save."""
        if not self.key:
            self.key = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.user.username})"

    def revoke(self) -> None:
        """Revoke this API key."""
        self.is_active = False
        self.revoked_at = timezone.now()
        self.save(update_fields=['is_active', 'revoked_at', 'updated_at'])
