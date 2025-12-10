"""Serializers for CMS app."""

from rest_framework import serializers
from .models import ManagedContent


class ManagedContentSerializer(serializers.ModelSerializer):
    """Serializer for managed content."""

    file_path = serializers.CharField(source='file.path', read_only=True)

    class Meta:
        model = ManagedContent
        fields = [
            'id',
            'file_path',
            'rendered_html',
            'rendered_at',
            'created_at',
        ]
        read_only_fields = fields
