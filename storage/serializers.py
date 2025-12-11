"""Serializers for storage app."""

from rest_framework import serializers
from .models import StoredFile


class StoredFileSerializer(serializers.ModelSerializer):
    """Serializer for file metadata."""

    class Meta:
        model = StoredFile
        fields = [
            'id',
            'path',
            'name',
            'size',
            'content_type',
            'is_directory',
            'parent_path',
            'created_at',
            'updated_at',
            'encryption_method',
            'key_id',
            'encrypted_filename',
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
    encryption_method = serializers.CharField(required=False, default='none')


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
    encryption_method = serializers.CharField(required=False, default='none')
