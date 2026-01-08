"""Serializers for CMS app."""

from rest_framework import serializers

from .models import ManagedContent, PageFileMapping


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
