from django.db import models
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

    def __str__(self):
        return f"CMS: {self.file.path}"
