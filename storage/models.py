import uuid
from typing import List, Tuple

from django.core.exceptions import ValidationError
from django.db import models

from core.models import AbstractBaseModel


class StoredFile(AbstractBaseModel):
    """
    File metadata index for fast queries.

    The storage backend (filesystem) is the source of truth.
    This model is a rebuildable index.

    Encryption metadata is stored per ADR 006 to support future encryption features.
    """

    # Encryption method choices (ADR 006, ADR 010)
    ENCRYPTION_NONE = "none"
    ENCRYPTION_SERVER = "server"
    ENCRYPTION_SERVER_USER = "server-user"  # Future: per-user derived keys
    ENCRYPTION_CLIENT = "client"  # Future: user-held keys
    ENCRYPTION_CHOICES = [
        (ENCRYPTION_NONE, "No encryption"),
        (ENCRYPTION_SERVER, "Server-side (master key)"),
        (ENCRYPTION_SERVER_USER, "Server-side (per-user key)"),
        (ENCRYPTION_CLIENT, "Client-side (user holds key)"),
    ]

    owner = models.ForeignKey(
        "accounts.Account", on_delete=models.CASCADE, related_name="files"
    )
    path = models.CharField(
        max_length=1024
    )  # Full path including filename, relative to user root
    name = models.CharField(max_length=255)  # Filename only
    size = models.BigIntegerField(default=0)
    content_type = models.CharField(max_length=100, blank=True)
    is_directory = models.BooleanField(default=False)
    parent_path = models.CharField(
        max_length=1024, blank=True
    )  # For efficient directory listing

    # Custom sort order (null = alphabetical default)
    sort_position = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Custom sort position (lower = first, null = alphabetical)",
    )

    # Encryption metadata (ADR 006)
    encryption_method = models.CharField(
        max_length=20,
        choices=ENCRYPTION_CHOICES,
        default=ENCRYPTION_NONE,
        help_text="Encryption method used for this file",
    )
    key_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Identifier for encryption key (for key rotation)",
    )
    encrypted_filename = models.CharField(
        max_length=1024,
        blank=True,
        null=True,
        help_text="Encrypted filename for client-side encrypted files",
    )
    encrypted_size = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Size on disk including encryption overhead (ADR 010)",
    )

    class Meta:
        verbose_name = "Stored File"
        verbose_name_plural = "Stored Files"
        unique_together = ["owner", "path"]
        indexes = [
            models.Index(fields=["owner", "parent_path"]),
            models.Index(fields=["owner", "path"]),
            models.Index(
                fields=["encryption_method"]
            ),  # For querying by encryption status
        ]
        ordering = ["path"]

    def clean(self):
        """Validate encryption metadata per ADR 006 governance."""
        super().clean()
        if not self.encryption_method:
            raise ValidationError(
                "encryption_method must be set (ADR 006 fitness function)"
            )

    def __str__(self):
        return f"{self.owner.user.username}: {self.path}"


class ShareLink(AbstractBaseModel):
    """Public share link for a file."""

    # Expiry choices
    EXPIRY_1_DAY = 1
    EXPIRY_3_DAYS = 3
    EXPIRY_7_DAYS = 7
    EXPIRY_30_DAYS = 30
    EXPIRY_90_DAYS = 90
    EXPIRY_UNLIMITED = 0

    EXPIRY_CHOICES = [
        (EXPIRY_1_DAY, "1 day"),
        (EXPIRY_3_DAYS, "3 days"),
        (EXPIRY_7_DAYS, "7 days"),
        (EXPIRY_30_DAYS, "30 days"),
        (EXPIRY_90_DAYS, "90 days"),
        (EXPIRY_UNLIMITED, "Never"),
    ]

    owner = models.ForeignKey(
        "accounts.Account", on_delete=models.CASCADE, related_name="share_links"
    )

    # What file this shares
    stored_file = models.ForeignKey(
        "StoredFile",
        on_delete=models.CASCADE,
        related_name="share_links",
        help_text="The file being shared",
    )

    # Legacy field synced from stored_file.path for API compatibility
    file_path = models.CharField(
        max_length=1024,
        editable=False,
        help_text="Auto-populated from stored_file.path",
    )

    # Auto-generated UUID token
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)

    # Optional custom slug (user-friendly URL)
    custom_slug = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="Custom URL slug (alphanumeric and hyphens, 3-64 chars)",
    )

    # Optional password protection (use Django's make_password)
    password_hash = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Hashed password for protected links",
    )

    # Expiry
    expiry_days = models.IntegerField(
        choices=EXPIRY_CHOICES,
        default=EXPIRY_7_DAYS,
        help_text="Number of days until link expires (0 = never)",
    )
    expires_at = models.DateTimeField(
        blank=True, null=True, help_text="Calculated expiration timestamp"
    )

    # Permissions (for future directory sharing)
    allow_download = models.BooleanField(
        default=True, help_text="Allow file download (for future read-only links)"
    )

    # Analytics
    view_count = models.PositiveIntegerField(
        default=0, help_text="Number of times this link's info was viewed"
    )
    download_count = models.PositiveIntegerField(
        default=0, help_text="Number of times the file was downloaded"
    )
    last_accessed_at = models.DateTimeField(
        blank=True, null=True, help_text="Last time this link was viewed or downloaded"
    )

    # Revocation
    is_active = models.BooleanField(
        default=True, help_text="Whether this link is active (false = revoked)"
    )

    class Meta:
        verbose_name = "Share Link"
        verbose_name_plural = "Share Links"
        indexes = [
            models.Index(fields=["owner", "stored_file"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["is_active"]),
        ]
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        """Calculate expires_at from expiry_days on save."""
        if self.expiry_days == self.EXPIRY_UNLIMITED:
            self.expires_at = None
        elif not self.expires_at:
            # Only auto-calculate if not manually set
            from datetime import timedelta

            from django.utils import timezone

            self.expires_at = timezone.now() + timedelta(days=self.expiry_days)

        # Sync file_path for backward compatibility
        if self.stored_file:
            self.file_path = self.stored_file.path

        super().save(*args, **kwargs)

    @property
    def file_name(self) -> str:
        """Get the name of the shared file."""
        return (
            self.stored_file.name if self.stored_file else self.file_path.split("/")[-1]
        )

    def is_expired(self) -> bool:
        """Check if this link has expired."""
        if self.expires_at is None:
            return False
        from django.utils import timezone

        return timezone.now() > self.expires_at

    def is_valid(self) -> bool:
        """Check if this link is active and not expired."""
        return self.is_active and not self.is_expired()

    def get_public_url_key(self) -> str:
        """Return custom_slug if set, otherwise token string."""
        return self.custom_slug or str(self.token)

    def check_password(self, raw_password: str) -> bool:
        """Check if provided password matches (or if no password set)."""
        if not self.password_hash:
            return True  # No password set, always valid
        from django.contrib.auth.hashers import check_password

        return check_password(raw_password, self.password_hash)

    def set_password(self, raw_password: str) -> None:
        """Hash and set password, or clear if None/empty."""
        if raw_password:
            from django.contrib.auth.hashers import make_password

            self.password_hash = make_password(raw_password)
        else:
            self.password_hash = None

    def __str__(self):
        key = self.get_public_url_key()
        return f"{self.owner.user.username}: {self.file_path} ({key})"


class FileAuditLog(AbstractBaseModel):
    """
    Complete audit trail for all file operations.

    Tracks who did what to which file, when, and with what result.
    Designed for security auditing, compliance, and troubleshooting.

    Key distinction:
    - performed_by: The user who actually performed the action (e.g., an admin)
    - target_user: The user whose files were affected
    - is_admin_action: True when an admin acts on another user's files
    """

    # Action type constants
    ACTION_LIST = "list"
    ACTION_UPLOAD = "upload"
    ACTION_DOWNLOAD = "download"
    ACTION_DELETE = "delete"
    ACTION_MOVE = "move"
    ACTION_COPY = "copy"
    ACTION_EDIT = "edit"
    ACTION_PREVIEW = "preview"
    ACTION_CREATE_DIR = "create_dir"
    ACTION_BULK_DELETE = "bulk_delete"
    ACTION_BULK_MOVE = "bulk_move"
    ACTION_BULK_COPY = "bulk_copy"

    ACTION_CHOICES: List[Tuple[str, str]] = [
        (ACTION_LIST, "List directory"),
        (ACTION_UPLOAD, "Upload file"),
        (ACTION_DOWNLOAD, "Download file"),
        (ACTION_DELETE, "Delete file"),
        (ACTION_MOVE, "Move file"),
        (ACTION_COPY, "Copy file"),
        (ACTION_EDIT, "Edit content"),
        (ACTION_PREVIEW, "Preview content"),
        (ACTION_CREATE_DIR, "Create directory"),
        (ACTION_BULK_DELETE, "Bulk delete"),
        (ACTION_BULK_MOVE, "Bulk move"),
        (ACTION_BULK_COPY, "Bulk copy"),
    ]

    # Who performed the action (the admin for admin actions, or the account for regular actions)
    performed_by = models.ForeignKey(
        "accounts.Account",
        on_delete=models.SET_NULL,
        null=True,
        related_name="file_actions_performed",
        help_text="Account who performed the action (admin for admin actions)",
    )

    # Whose files were affected (the target account)
    target_user = models.ForeignKey(
        "accounts.Account",
        on_delete=models.SET_NULL,
        null=True,
        related_name="file_actions_received",
        help_text="Account whose files were affected",
    )

    # Is this an admin action (acting on behalf of another user)?
    is_admin_action = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if admin acted on another user's files",
    )

    # The action performed
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        db_index=True,
    )

    # File/path information
    path = models.CharField(
        max_length=1024,
        help_text="Primary path affected",
    )
    destination_path = models.CharField(
        max_length=1024,
        blank=True,
        null=True,
        help_text="Destination path for move/copy operations",
    )

    # For bulk operations - list of paths affected
    paths_affected = models.JSONField(
        blank=True,
        null=True,
        help_text="List of paths for bulk operations",
    )

    # Result
    success = models.BooleanField(default=True)
    error_code = models.CharField(max_length=50, blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)

    # Request metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True, null=True)

    # File metadata at time of action (for forensics)
    file_size = models.BigIntegerField(null=True, blank=True)
    content_type = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = "File Audit Log"
        verbose_name_plural = "File Audit Logs"
        indexes = [
            models.Index(fields=["performed_by", "-created_at"]),
            models.Index(fields=["target_user", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        admin_marker = "[ADMIN] " if self.is_admin_action else ""
        performer = self.performed_by.user.username if self.performed_by else "N/A"
        return f"{admin_marker}{performer}: {self.action} {self.path}"
