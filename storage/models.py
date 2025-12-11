from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from core.models import AbstractBaseModel


class StoredFile(AbstractBaseModel):
    """
    File metadata index for fast queries.

    The storage backend (filesystem) is the source of truth.
    This model is a rebuildable index.

    Encryption metadata is stored per ADR 006 to support future encryption features.
    """

    # Encryption method choices (ADR 006)
    ENCRYPTION_NONE = 'none'
    ENCRYPTION_SERVER = 'server'
    ENCRYPTION_CLIENT = 'client'
    ENCRYPTION_CHOICES = [
        (ENCRYPTION_NONE, 'No encryption'),
        (ENCRYPTION_SERVER, 'Server-side encryption'),
        (ENCRYPTION_CLIENT, 'Client-side encryption'),
    ]

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

    # Encryption metadata (ADR 006)
    encryption_method = models.CharField(
        max_length=20,
        choices=ENCRYPTION_CHOICES,
        default=ENCRYPTION_NONE,
        help_text="Encryption method used for this file"
    )
    key_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Identifier for encryption key (for key rotation)"
    )
    encrypted_filename = models.CharField(
        max_length=1024,
        blank=True,
        null=True,
        help_text="Encrypted filename for client-side encrypted files"
    )

    class Meta:
        verbose_name = "Stored File"
        verbose_name_plural = "Stored Files"
        unique_together = ['owner', 'path']
        indexes = [
            models.Index(fields=['owner', 'parent_path']),
            models.Index(fields=['owner', 'path']),
            models.Index(fields=['encryption_method']),  # For querying by encryption status
        ]
        ordering = ['path']

    def clean(self):
        """Validate encryption metadata per ADR 006 governance."""
        super().clean()
        if not self.encryption_method:
            raise ValidationError("encryption_method must be set (ADR 006 fitness function)")

    def __str__(self):
        return f"{self.owner.username}: {self.path}"
