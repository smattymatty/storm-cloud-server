from django.db import models
from django.contrib.auth import get_user_model
from core.models import AbstractBaseModel


class StoredFile(AbstractBaseModel):
    """
    File metadata index for fast queries.

    The storage backend (filesystem) is the source of truth.
    This model is a rebuildable index.
    """

    owner = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        related_name='files'
    )
    path = models.CharField(max_length=1024)  # Full path including filename, relative to user root
    name = models.CharField(max_length=255)   # Filename only
    size = models.BigIntegerField(default=0)
    content_type = models.CharField(max_length=100, blank=True)
    is_directory = models.BooleanField(default=False)
    parent_path = models.CharField(max_length=1024, blank=True)  # For efficient directory listing

    class Meta:
        verbose_name = "Stored File"
        verbose_name_plural = "Stored Files"
        unique_together = ['owner', 'path']
        indexes = [
            models.Index(fields=['owner', 'parent_path']),
            models.Index(fields=['owner', 'path']),
        ]
        ordering = ['path']

    def __str__(self):
        return f"{self.owner.username}: {self.path}"
