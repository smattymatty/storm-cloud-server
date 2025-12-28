"""Serializers for storage app."""

import re

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import ShareLink, StoredFile


class StoredFileSerializer(serializers.ModelSerializer):
    """Serializer for file metadata."""

    class Meta:
        model = StoredFile
        fields = [
            "id",
            "path",
            "name",
            "size",
            "content_type",
            "is_directory",
            "parent_path",
            "created_at",
            "updated_at",
            "encryption_method",
            "key_id",
            "encrypted_filename",
        ]
        read_only_fields = fields


class FileListItemSerializer(serializers.Serializer):
    """CLI-friendly file list item."""

    name = serializers.CharField()
    path = serializers.CharField()
    size = serializers.IntegerField()
    is_directory = serializers.BooleanField()
    content_type = serializers.CharField(allow_null=True)
    modified_at = serializers.DateTimeField()
    encryption_method = serializers.CharField(required=False, default="none")
    sort_position = serializers.IntegerField(allow_null=True, required=False)


class DirectoryListResponseSerializer(serializers.Serializer):
    """Response for directory listing."""

    path = serializers.CharField()
    entries = FileListItemSerializer(many=True)
    total = serializers.IntegerField()


class FileUploadSerializer(serializers.Serializer):
    """Serializer for file upload."""

    file = serializers.FileField()


class FileInfoResponseSerializer(serializers.Serializer):
    """Response for file info endpoint."""

    path = serializers.CharField()
    name = serializers.CharField()
    size = serializers.IntegerField()
    content_type = serializers.CharField(allow_null=True)
    is_directory = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    modified_at = serializers.DateTimeField()
    encryption_method = serializers.CharField(required=False, default="none")


# =============================================================================
# Share Link Serializers
# =============================================================================


class ShareLinkCreateSerializer(serializers.Serializer):
    """Serializer for creating share links."""

    file_path = serializers.CharField(max_length=1024)
    expiry_days = serializers.ChoiceField(
        choices=[0, 1, 3, 7, 30, 90], required=False, allow_null=True
    )
    password = serializers.CharField(
        max_length=128, required=False, allow_blank=True, write_only=True
    )
    custom_slug = serializers.CharField(max_length=64, required=False, allow_blank=True)

    def validate_custom_slug(self, value):
        """Validate custom slug format and uniqueness."""
        if not value:
            return None

        # Alphanumeric and hyphens only, 3-64 chars
        if not re.match(r"^[a-zA-Z0-9-]{3,64}$", value):
            raise serializers.ValidationError(
                "Slug must be 3-64 characters, alphanumeric and hyphens only"
            )

        # Check uniqueness
        if ShareLink.objects.filter(custom_slug=value).exists():
            raise serializers.ValidationError("This slug is already taken")

        return value


class ShareLinkResponseSerializer(serializers.ModelSerializer):
    """Serializer for share link responses."""

    url = serializers.SerializerMethodField()
    has_password = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()

    class Meta:
        model = ShareLink
        fields = [
            "id",
            "owner",
            "file_path",
            "token",
            "custom_slug",
            "url",
            "has_password",
            "expiry_days",
            "expires_at",
            "created_at",
            "view_count",
            "download_count",
            "last_accessed_at",
            "is_active",
            "is_expired",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_url(self, obj: ShareLink) -> str:
        """Build full public URL for this share link."""
        key = obj.get_public_url_key()
        return f"/api/v1/public/{key}/"

    @extend_schema_field(serializers.BooleanField())
    def get_has_password(self, obj: ShareLink) -> bool:
        """Check if this link has password protection."""
        return bool(obj.password_hash)

    @extend_schema_field(serializers.BooleanField())
    def get_is_expired(self, obj: ShareLink) -> bool:
        """Check if this link has expired."""
        return obj.is_expired()


class PublicShareInfoSerializer(serializers.Serializer):
    """Serializer for public share file info."""

    name = serializers.CharField()
    size = serializers.IntegerField()
    content_type = serializers.CharField()
    requires_password = serializers.BooleanField()
    download_url = serializers.CharField()


# =============================================================================
# Directory Reorder Serializers
# =============================================================================


class DirectoryReorderSerializer(serializers.Serializer):
    """Serializer for reordering files in a directory."""

    order = serializers.ListField(
        child=serializers.CharField(max_length=255),
        min_length=1,
        help_text="List of filenames in desired order (partial list allowed)",
    )


# =============================================================================
# Bulk Operations Serializers
# =============================================================================


class BulkOperationRequestSerializer(serializers.Serializer):
    """Serializer for bulk operation requests."""

    operation = serializers.ChoiceField(
        choices=["delete", "move", "copy"], help_text="Operation to perform on files"
    )
    paths = serializers.ListField(
        child=serializers.CharField(max_length=1024),
        min_length=1,
        max_length=250,
        help_text="List of file/directory paths (1-250 items)",
    )
    options = serializers.DictField(
        required=False,
        allow_null=True,
        help_text="Operation-specific options (e.g., destination for move/copy)",
    )

    def validate(self, data):
        """Validate operation-specific requirements."""
        operation = data.get("operation")
        options = data.get("options", {})

        # Move and copy require destination
        if operation in ["move", "copy"]:
            if not options or "destination" not in options:
                raise serializers.ValidationError(
                    {"options": f"Destination is required for {operation} operation"}
                )

        return data


class BulkOperationResultSerializer(serializers.Serializer):
    """Serializer for individual file operation result."""

    path = serializers.CharField()
    success = serializers.BooleanField()
    error_code = serializers.CharField(allow_null=True, required=False)
    error_message = serializers.CharField(allow_null=True, required=False)
    data = serializers.DictField(allow_null=True, required=False)  # type: ignore[assignment]


class BulkOperationResponseSerializer(serializers.Serializer):
    """Serializer for bulk operation response (sync)."""

    operation = serializers.CharField()
    total = serializers.IntegerField()
    succeeded = serializers.IntegerField()
    failed = serializers.IntegerField()
    results = BulkOperationResultSerializer(many=True)


class BulkOperationAsyncResponseSerializer(serializers.Serializer):
    """Serializer for bulk operation async response."""

    async_field = serializers.BooleanField(source="async")
    task_id = serializers.CharField()
    total = serializers.IntegerField()
    status_url = serializers.CharField()


class BulkOperationStatusResponseSerializer(serializers.Serializer):
    """Serializer for bulk operation status check."""

    task_id = serializers.CharField()
    status = serializers.ChoiceField(choices=["running", "complete", "failed"])
    operation = serializers.CharField(required=False, allow_null=True)
    total = serializers.IntegerField(required=False, allow_null=True)
    succeeded = serializers.IntegerField(required=False, allow_null=True)
    failed = serializers.IntegerField(required=False, allow_null=True)
    results = BulkOperationResultSerializer(many=True, required=False)
    error = serializers.CharField(required=False, allow_null=True)
    progress = serializers.DictField(required=False, allow_null=True)
