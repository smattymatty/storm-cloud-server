"""Serializers for CMS app."""

from typing import Any

from rest_framework import serializers

from .models import ContentFlag, ContentFlagHistory, ManagedContent, PageFileMapping
from .validators import validate_flag_metadata


class ManagedContentSerializer(serializers.ModelSerializer):
    """Serializer for managed content."""

    file_path = serializers.CharField(source="file.path", read_only=True)

    class Meta:
        model = ManagedContent
        fields = [
            "id",
            "file_path",
            "rendered_html",
            "rendered_at",
            "created_at",
        ]
        read_only_fields = fields


# =============================================================================
# Page-File Mapping Serializers
# =============================================================================


class MappingReportSerializer(serializers.Serializer):
    """Incoming mapping report from Glue middleware.

    file_paths is optional:
    - If provided: Update page-file mappings + increment view count
    - If omitted: Just increment view count (view ping)
    """

    page_path = serializers.CharField(max_length=500)
    file_paths = serializers.ListField(
        child=serializers.CharField(max_length=500),
        max_length=100,  # Reasonable limit per page
        required=False,
        allow_null=True,
        default=None,
    )


class PageSummarySerializer(serializers.Serializer):
    """Page with file count for list view."""

    page_path = serializers.CharField()
    file_count = serializers.IntegerField()
    first_seen = serializers.DateTimeField()
    last_seen = serializers.DateTimeField()
    is_stale = serializers.BooleanField()
    staleness_hours = serializers.IntegerField(allow_null=True)


class FileOnPageSerializer(serializers.Serializer):
    """File mapping for page detail view."""

    file_path = serializers.CharField()
    first_seen = serializers.DateTimeField()
    last_seen = serializers.DateTimeField()
    is_stale = serializers.BooleanField()
    staleness_hours = serializers.IntegerField(allow_null=True)
    flags = serializers.DictField(
        child=serializers.BooleanField(),
        help_text="Content flags (ai_generated, user_approved)",
    )


class PageDetailSerializer(serializers.Serializer):
    """Page with all its files."""

    page_path = serializers.CharField()
    files = FileOnPageSerializer(many=True)
    first_seen = serializers.DateTimeField()
    last_seen = serializers.DateTimeField()
    is_stale = serializers.BooleanField()


class PageUsingFileSerializer(serializers.Serializer):
    """Page reference for file detail view."""

    page_path = serializers.CharField()
    first_seen = serializers.DateTimeField()
    last_seen = serializers.DateTimeField()
    is_stale = serializers.BooleanField()


class FileDetailSerializer(serializers.Serializer):
    """File with all pages using it."""

    file_path = serializers.CharField()
    pages = PageUsingFileSerializer(many=True)
    page_count = serializers.IntegerField()


# =============================================================================
# Content Flag Serializers
# =============================================================================


class ContentFlagSerializer(serializers.ModelSerializer):
    """Read serializer for content flags."""

    file_path = serializers.CharField(source="stored_file.path", read_only=True)
    changed_by_username = serializers.CharField(
        source="changed_by.username", read_only=True, allow_null=True
    )

    class Meta:
        model = ContentFlag
        fields = [
            "id",
            "file_path",
            "flag_type",
            "is_active",
            "metadata",
            "changed_by_username",
            "changed_at",
        ]
        read_only_fields = fields


class SetFlagSerializer(serializers.Serializer):
    """Write serializer for setting a flag."""

    is_active = serializers.BooleanField()
    metadata = serializers.JSONField(required=False, default=dict)

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        flag_type = self.context.get("flag_type")
        if not flag_type:
            raise serializers.ValidationError("flag_type must be provided in context")

        is_valid, error = validate_flag_metadata(flag_type, data.get("metadata", {}))
        if not is_valid:
            raise serializers.ValidationError({"metadata": error})
        return data


class FlagHistorySerializer(serializers.ModelSerializer):
    """Serializer for flag history entries."""

    changed_by_username = serializers.CharField(
        source="changed_by.username", read_only=True, allow_null=True
    )

    class Meta:
        model = ContentFlagHistory
        fields = [
            "id",
            "was_active",
            "is_active",
            "metadata",
            "changed_by_username",
            "changed_at",
        ]
        read_only_fields = fields


class FileWithFlagsSerializer(serializers.Serializer):
    """File summary with flag status for list views."""

    file_path = serializers.CharField()
    file_name = serializers.CharField()
    ai_generated = serializers.BooleanField(allow_null=True)
    user_approved = serializers.BooleanField(allow_null=True)
    needs_review = serializers.BooleanField()
    last_flag_change = serializers.DateTimeField(allow_null=True)
