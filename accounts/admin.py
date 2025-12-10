from django.contrib import admin
from .models import APIKey


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    """Admin interface for API keys."""

    list_display = ['name', 'user', 'is_active', 'created_at', 'last_used_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'user__username', 'user__email']
    readonly_fields = ['id', 'key', 'created_at', 'updated_at', 'last_used_at']

    fields = ['user', 'name', 'is_active', 'key', 'created_at', 'updated_at', 'last_used_at']

    def get_readonly_fields(self, request, obj=None):
        """Make key readonly after creation."""
        if obj:  # Editing existing object
            return self.readonly_fields + ['user']
        return self.readonly_fields
