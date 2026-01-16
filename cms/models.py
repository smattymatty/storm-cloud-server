from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import AbstractBaseModel
from storage.models import StoredFile


class ManagedContent(AbstractBaseModel):
    """
    Tracks which files are under CMS management for Spellbook rendering.

    Phase 1: This is a stub. Rendering not implemented.
    """

    file = models.OneToOneField(
        StoredFile, on_delete=models.CASCADE, related_name="cms_content"
    )

    # Cache rendered output
    rendered_html = models.TextField(blank=True)
    rendered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Managed Content"
        verbose_name_plural = "Managed Content"

    def __str__(self) -> str:
        return f"CMS: {self.file.path}"


class PageFileMapping(AbstractBaseModel):
    """
    Tracks which content files are used on which pages.

    Reported by Storm Cloud Glue middleware during page requests.
    Enables page-based content browsing in the UI.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="page_file_mappings",
        help_text="User who owns this content (identified by API key)",
    )

    page_path = models.CharField(
        max_length=500,
        db_index=True,
        help_text="URL path of the page (e.g., '/about/')",
    )

    file_path = models.CharField(
        max_length=500,
        db_index=True,
        help_text="Path to content file (e.g., 'pages/about.md')",
    )

    first_seen = models.DateTimeField(
        auto_now_add=True,
        help_text="When this mapping was first reported",
    )

    last_seen = models.DateTimeField(
        auto_now=True,
        help_text="When this mapping was last reported",
    )

    class Meta:
        verbose_name = "Page File Mapping"
        verbose_name_plural = "Page File Mappings"
        unique_together = ["owner", "page_path", "file_path"]
        ordering = ["-last_seen"]
        indexes = [
            models.Index(fields=["owner", "page_path"]),
            models.Index(fields=["owner", "file_path"]),
            models.Index(fields=["last_seen"]),
        ]

    def __str__(self) -> str:
        return f"{self.page_path} → {self.file_path}"

    @property
    def is_stale(self) -> bool:
        """Mapping not seen in 24 hours."""
        threshold = timezone.now() - timedelta(hours=24)
        return self.last_seen < threshold

    @property
    def staleness_hours(self) -> int | None:
        """Hours since last seen, or None if fresh."""
        if not self.is_stale:
            return None
        delta = timezone.now() - self.last_seen
        return int(delta.total_seconds() / 3600)

    @classmethod
    def get_stale_mappings(cls, owner, hours: int = 24):
        """Get mappings not seen in specified hours."""
        threshold = timezone.now() - timedelta(hours=hours)
        return cls.objects.filter(owner=owner, last_seen__lt=threshold)

    @classmethod
    def cleanup_stale(cls, owner, hours: int = 168) -> int:
        """Delete mappings not seen in specified hours (default 7 days)."""
        threshold = timezone.now() - timedelta(hours=hours)
        deleted, _ = cls.objects.filter(owner=owner, last_seen__lt=threshold).delete()
        return deleted


class PageStats(AbstractBaseModel):
    """
    Tracks view counts per page.

    Incremented each time Glue middleware reports a page→files mapping.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="page_stats",
        help_text="User who owns this page (identified by API key)",
    )

    page_path = models.CharField(
        max_length=500,
        db_index=True,
        help_text="URL path of the page (e.g., '/about/')",
    )

    view_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times this page has been viewed",
    )

    first_viewed = models.DateTimeField(
        auto_now_add=True,
        help_text="When this page was first viewed",
    )

    last_viewed = models.DateTimeField(
        auto_now=True,
        help_text="When this page was last viewed",
    )

    class Meta:
        verbose_name = "Page Stats"
        verbose_name_plural = "Page Stats"
        unique_together = ["owner", "page_path"]
        ordering = ["-view_count"]
        indexes = [
            models.Index(fields=["owner", "page_path"]),
        ]

    def __str__(self) -> str:
        return f"{self.page_path} ({self.view_count} views)"


class ContentFlag(AbstractBaseModel):
    """
    A flag on a content file with type-specific metadata.

    Each file can have multiple flags (one per type). Used to track
    AI-generated content and client approval status for transparency
    and workflow management.

    Filesystem wins architecture: if file deleted, cascade delete the flag.
    """

    class FlagType(models.TextChoices):
        AI_GENERATED = "ai_generated", "AI Generated"
        USER_APPROVED = "user_approved", "User Approved"
        # Future: NEEDS_LEGAL_REVIEW, CLIENT_EDITED, PLACEHOLDER, etc.

    stored_file = models.ForeignKey(
        StoredFile,
        on_delete=models.CASCADE,
        related_name="content_flags",
        help_text="The file being flagged",
    )

    flag_type = models.CharField(
        max_length=50,
        choices=FlagType.choices,
        help_text="Type of flag (ai_generated, user_approved, etc.)",
    )

    is_active = models.BooleanField(
        default=False,
        help_text="Whether this flag is currently active",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Type-specific metadata (schema varies by flag_type)",
    )

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="flag_changes",
        help_text="User who last changed this flag",
    )

    changed_at = models.DateTimeField(
        auto_now=True,
        help_text="When this flag was last changed",
    )

    class Meta:
        verbose_name = "Content Flag"
        verbose_name_plural = "Content Flags"
        unique_together = ["stored_file", "flag_type"]
        indexes = [
            models.Index(fields=["stored_file", "flag_type"]),
            models.Index(fields=["flag_type", "is_active"]),
        ]

    def __str__(self) -> str:
        status = "active" if self.is_active else "inactive"
        return f"{self.stored_file.path} [{self.flag_type}: {status}]"

    def save(self, *args, **kwargs):
        # Create history entry on updates (not initial creation)
        # Note: get_or_create uses defaults directly, doesn't call save() for create
        if self.pk:
            try:
                old = ContentFlag.objects.get(pk=self.pk)
                ContentFlagHistory.objects.create(
                    flag=self,
                    was_active=old.is_active,
                    is_active=self.is_active,
                    metadata=self.metadata.copy() if self.metadata else {},
                    changed_by=self.changed_by,
                )
            except ContentFlag.DoesNotExist:
                pass  # New object, no history needed
        super().save(*args, **kwargs)


class ContentFlagHistory(AbstractBaseModel):
    """
    Audit trail for flag changes.

    Created automatically when a ContentFlag is updated via save().
    Tracks who changed what, when, and the state transition.
    """

    flag = models.ForeignKey(
        ContentFlag,
        on_delete=models.CASCADE,
        related_name="history",
        help_text="The flag that was changed",
    )

    was_active = models.BooleanField(
        help_text="Previous is_active state",
    )

    is_active = models.BooleanField(
        help_text="New is_active state",
    )

    metadata = models.JSONField(
        default=dict,
        help_text="Metadata snapshot at time of change",
    )

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="User who made this change",
    )

    changed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this change occurred",
    )

    class Meta:
        verbose_name = "Content Flag History"
        verbose_name_plural = "Content Flag History"
        ordering = ["-changed_at"]

    def __str__(self) -> str:
        return f"{self.flag} changed at {self.changed_at}"
