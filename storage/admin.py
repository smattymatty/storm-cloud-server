from django.contrib import admin
from .models import StoredFile


@admin.register(StoredFile)
class StoredFileAdmin(admin.ModelAdmin):
    """Admin interface for stored files."""

    list_display = ['path', 'owner', 'name', 'size', 'is_directory', 'created_at']
    list_filter = ['is_directory', 'owner', 'created_at']
    search_fields = ['path', 'name', 'owner__username']
    readonly_fields = ['id', 'created_at', 'updated_at']

    fields = ['owner', 'path', 'name', 'size', 'content_type', 'is_directory', 'parent_path', 'created_at', 'updated_at']
