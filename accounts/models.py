from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify
from datetime import timedelta
from core.models import AbstractBaseModel
import secrets


def generate_verification_token() -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(48)


def generate_enrollment_key() -> str:
    """Generate a secure enrollment key with prefix."""
    return f"ek_{secrets.token_urlsafe(32)}"


def generate_platform_invite_key() -> str:
    """Generate a secure platform invite key with prefix."""
    return f"pi_{secrets.token_urlsafe(32)}"


class Organization(AbstractBaseModel):
    """
    Top-level tenant container.

    Organizations group accounts and own API keys. All files belong to accounts
    within an organization.
    """

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=255)

    # Org-level storage quota (optional - 0 = unlimited)
    storage_quota_bytes = models.BigIntegerField(
        default=0, help_text="Maximum storage for entire org in bytes. 0 = unlimited."
    )
    storage_used_bytes = models.BigIntegerField(
        default=0, help_text="Current storage usage across all accounts."
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Auto-generate slug from name if not provided."""
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Organization.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def storage_remaining_bytes(self) -> int:
        """Bytes remaining in org quota. Returns -1 if unlimited."""
        if self.storage_quota_bytes == 0:
            return -1
        return max(0, self.storage_quota_bytes - self.storage_used_bytes)

    @property
    def is_over_quota(self) -> bool:
        """Check if org has exceeded storage quota."""
        if self.storage_quota_bytes == 0:
            return False
        return self.storage_used_bytes >= self.storage_quota_bytes

    def update_storage_usage(self, delta_bytes: int) -> None:
        """Update storage usage by delta (positive or negative)."""
        self.storage_used_bytes = max(0, self.storage_used_bytes + delta_bytes)
        self.save(update_fields=["storage_used_bytes", "updated_at"])


class Account(AbstractBaseModel):
    """
    Extended user profile with organization membership.

    Replaces UserProfile. Each Account belongs to exactly one Organization.
    Files, shares, and quotas are tied to Accounts.
    """

    user = models.OneToOneField(
        get_user_model(), on_delete=models.CASCADE, related_name="account"
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="accounts"
    )
    email_verified = models.BooleanField(default=False)

    # Per-account storage quota (optional - 0 = use org default)
    storage_quota_bytes = models.BigIntegerField(
        default=0, help_text="Maximum storage for this account in bytes. 0 = unlimited."
    )
    storage_used_bytes = models.BigIntegerField(
        default=0, help_text="Current storage usage in bytes."
    )

    # Action permissions (migrated from UserProfile)
    can_upload = models.BooleanField(
        default=True, help_text="Account can upload new files."
    )
    can_delete = models.BooleanField(
        default=True, help_text="Account can delete files and folders."
    )
    can_move = models.BooleanField(
        default=True, help_text="Account can move/rename files and folders."
    )
    can_overwrite = models.BooleanField(
        default=True, help_text="Account can overwrite/edit existing files."
    )
    can_create_shares = models.BooleanField(
        default=True, help_text="Account can create share links."
    )
    max_share_links = models.PositiveIntegerField(
        default=0, help_text="Maximum active share links allowed. 0 = unlimited."
    )
    max_upload_bytes = models.BigIntegerField(
        default=0,
        help_text="Per-file upload size limit in bytes. 0 = use server default.",
    )

    # Org admin permissions (NEW)
    can_invite = models.BooleanField(
        default=False, help_text="Account can create enrollment keys to invite others."
    )
    can_manage_members = models.BooleanField(
        default=False,
        help_text="Account can view and modify other accounts in the org.",
    )
    can_manage_api_keys = models.BooleanField(
        default=False, help_text="Account can create and revoke org API keys."
    )
    is_owner = models.BooleanField(
        default=False,
        help_text="Account is an org owner. At least one owner must exist per org.",
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Account"
        verbose_name_plural = "Accounts"
        # Ensure one account per user
        constraints = [
            models.UniqueConstraint(fields=["user"], name="unique_user_account"),
        ]

    def __str__(self):
        return f"{self.user.username} @ {self.organization.name}"

    @property
    def storage_remaining_bytes(self) -> int:
        """Bytes remaining in quota. Returns -1 if unlimited."""
        if self.storage_quota_bytes == 0:
            return -1
        return max(0, self.storage_quota_bytes - self.storage_used_bytes)

    @property
    def is_over_quota(self) -> bool:
        """Check if account has exceeded storage quota."""
        if self.storage_quota_bytes == 0:
            return False
        return self.storage_used_bytes >= self.storage_quota_bytes

    def update_storage_usage(self, delta_bytes: int) -> None:
        """Update storage usage by delta (positive or negative)."""
        self.storage_used_bytes = max(0, self.storage_used_bytes + delta_bytes)
        self.save(update_fields=["storage_used_bytes", "updated_at"])
        # Also update org-level usage
        self.organization.update_storage_usage(delta_bytes)

    def delete(self, *args, **kwargs):
        """Prevent deleting the last owner of an organization."""
        if self.is_owner:
            owner_count = (
                Account.objects.filter(organization=self.organization, is_owner=True)
                .exclude(pk=self.pk)
                .count()
            )
            if owner_count == 0:
                raise ValueError("Cannot delete the last owner of an organization.")
        super().delete(*args, **kwargs)


class EnrollmentKey(AbstractBaseModel):
    """
    Invitation key for human account registration.

    EnrollmentKeys are created by org admins to invite new members.
    Can be single-use or multi-use, with optional email restrictions.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="enrollment_keys"
    )
    key = models.CharField(max_length=64, unique=True, default=generate_enrollment_key)
    name = models.CharField(
        max_length=255,
        help_text="Descriptive name, e.g., 'CEO Bootstrap', 'Sales Team Invite'",
    )

    # Email restriction (optional)
    required_email = models.EmailField(
        blank=True, null=True, help_text="If set, only this email can use this key."
    )

    # Preset permissions for accounts created with this key
    preset_permissions = models.JSONField(
        default=dict,
        blank=True,
        help_text="Permission overrides for accounts created with this key.",
    )

    # Usage tracking
    single_use = models.BooleanField(
        default=True, help_text="If true, key becomes invalid after first use."
    )
    used_by = models.ForeignKey(
        "Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="used_enrollment_key",
    )
    use_count = models.PositiveIntegerField(
        default=0, help_text="Number of times this key has been used."
    )
    used_at = models.DateTimeField(
        null=True, blank=True, help_text="When the key was first used."
    )

    # Expiration
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Key expires after this time. Null = never expires.",
    )

    # Audit
    created_by = models.ForeignKey(
        "Account",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_enrollment_keys",
    )

    is_active = models.BooleanField(default=True)
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this key was revoked. Null = not revoked.",
    )

    class Meta:
        verbose_name = "Enrollment Key"
        verbose_name_plural = "Enrollment Keys"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["key"]),
            models.Index(fields=["organization", "is_active"]),
        ]

    def __str__(self):
        status = "active" if self.is_valid() else "invalid"
        return f"{self.name} ({self.organization.name}) - {status}"

    def is_valid(self) -> bool:
        """Check if this enrollment key can be used."""
        if not self.is_active:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        if self.single_use and self.used_by:
            return False
        return True

    def mark_used(self, account: "Account") -> None:
        """Mark this key as used by an account."""
        self.use_count += 1
        if self.single_use:
            self.used_by = account
        # Set used_at only on first use
        if self.used_at is None:
            self.used_at = timezone.now()
        self.save(update_fields=["use_count", "used_by", "used_at", "updated_at"])


class EmailVerificationToken(AbstractBaseModel):
    """Token for email verification flow."""

    user = models.ForeignKey(
        get_user_model(), on_delete=models.CASCADE, related_name="verification_tokens"
    )
    token = models.CharField(
        max_length=64, unique=True, default=generate_verification_token
    )
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Email Verification Token"
        verbose_name_plural = "Email Verification Tokens"
        indexes = [
            models.Index(fields=["token"]),
            models.Index(fields=["user", "used_at"]),
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
        self.save(update_fields=["used_at"])


class APIKey(AbstractBaseModel):
    """
    API key for CLI/programmatic (machine) access.

    API keys are org-scoped and have their own permissions JSON.
    They are not tied to a specific account, but track who created them.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="api_keys"
    )
    created_by = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_api_keys",
        help_text="Account that created this key (for audit).",
    )

    name = models.CharField(max_length=100)  # e.g., "CLI key", "CI/CD key"
    key = models.CharField(max_length=64, unique=True, editable=False)
    last_used_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    # Permissions for this API key (independent of any account)
    permissions = models.JSONField(
        default=dict,
        blank=True,
        help_text="Permission flags for this key. Keys not present default to True.",
    )
    # Example: {"can_upload": true, "can_delete": false, "can_move": true}

    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when key was revoked. Set alongside is_active=False.",
    )

    # Webhook configuration (per-key notifications)
    webhook_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="URL to POST when content changes. Leave blank to disable.",
    )
    webhook_secret = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="HMAC secret for signing webhook payloads. Auto-generated.",
    )
    webhook_enabled = models.BooleanField(
        default=False, help_text="Whether webhook notifications are active."
    )
    webhook_last_triggered = models.DateTimeField(
        blank=True, null=True, help_text="Last time webhook was triggered."
    )
    webhook_last_status = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        choices=[
            ("success", "Success"),
            ("failed", "Failed"),
            ("timeout", "Timeout"),
        ],
        help_text="Status of last webhook delivery.",
    )

    class Meta:
        verbose_name = "API Key"
        verbose_name_plural = "API Keys"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        """Generate key on first save and handle webhook secret."""
        if not self.key:
            self.key = secrets.token_urlsafe(48)

        # Auto-generate webhook secret when URL is set
        if self.webhook_url and not self.webhook_secret:
            self.generate_webhook_secret()

        # Auto-enable/disable based on URL presence
        if self.webhook_url:
            self.webhook_enabled = True
        else:
            self.webhook_enabled = False
            self.webhook_secret = None

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.organization.name})"

    def generate_webhook_secret(self) -> str:
        """Generate a new webhook secret."""
        self.webhook_secret = secrets.token_hex(32)
        return self.webhook_secret

    def revoke(self) -> None:
        """Revoke this API key."""
        self.is_active = False
        self.revoked_at = timezone.now()
        self.save(update_fields=["is_active", "revoked_at", "updated_at"])

    def has_permission(self, permission_name: str) -> bool:
        """
        Check if this API key has a specific permission.

        Permissions not explicitly set default to True.
        """
        return self.permissions.get(permission_name, True)


class PlatformInvite(AbstractBaseModel):
    """
    Platform-level invitation for new client onboarding.

    Unlike EnrollmentKey (which is org-scoped), PlatformInvite is used
    to invite new clients who will create their own organization on signup.
    This enables client-first enrollment where the client creates the org.
    """

    key = models.CharField(
        max_length=64, unique=True, default=generate_platform_invite_key
    )
    email = models.EmailField(
        help_text="Email address that must be used to claim this invite."
    )
    name = models.CharField(
        max_length=255, help_text="Descriptive name, e.g., 'Acme Corp Onboarding'"
    )

    # Who created this invite (platform admin)
    created_by = models.ForeignKey(
        "Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_platform_invites",
        help_text="Platform admin who created this invite.",
    )

    # Usage tracking
    is_used = models.BooleanField(
        default=False, help_text="Whether this invite has been claimed."
    )
    used_by = models.ForeignKey(
        "Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="claimed_platform_invite",
        help_text="Account that claimed this invite.",
    )
    used_at = models.DateTimeField(
        null=True, blank=True, help_text="When the invite was claimed."
    )

    # Two-step enrollment tracking
    enrolled_user = models.OneToOneField(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pending_platform_invite",
        help_text="User who enrolled but hasn't created org yet.",
    )

    # Expiration
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Invite expires after this time. Null = never expires.",
    )

    # Org quota preset (applied when org is created)
    quota_bytes = models.BigIntegerField(
        default=0, help_text="Storage quota for the new org in bytes. 0 = unlimited."
    )

    is_active = models.BooleanField(default=True)
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this invite was revoked. Null = not revoked.",
    )

    class Meta:
        verbose_name = "Platform Invite"
        verbose_name_plural = "Platform Invites"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["key"]),
            models.Index(fields=["email"]),
            models.Index(fields=["is_active", "is_used"]),
        ]

    def __str__(self):
        status = (
            "used" if self.is_used else ("active" if self.is_valid() else "invalid")
        )
        return f"{self.name} ({self.email}) - {status}"

    def is_valid(self) -> bool:
        """Check if this invite can still be used."""
        if not self.is_active:
            return False
        if self.is_used:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True

    def mark_used(self, account: "Account") -> None:
        """Mark this invite as used by an account."""
        self.is_used = True
        self.used_by = account
        self.used_at = timezone.now()
        self.save(update_fields=["is_used", "used_by", "used_at", "updated_at"])
