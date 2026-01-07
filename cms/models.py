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
        StoredFile,
        on_delete=models.CASCADE,
        related_name='cms_content'
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
