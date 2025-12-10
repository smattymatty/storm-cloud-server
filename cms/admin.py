from django.contrib import admin
from .models import ManagedContent


@admin.register(ManagedContent)
class ManagedContentAdmin(admin.ModelAdmin):
    """Admin interface for managed content."""

    list_display = ['file', 'rendered_at', 'created_at']
    list_filter = ['rendered_at', 'created_at']
    search_fields = ['file__path', 'file__name']
    readonly_fields = ['id', 'created_at', 'updated_at', 'rendered_at']

    fields = ['file', 'rendered_html', 'rendered_at', 'created_at', 'updated_at']
