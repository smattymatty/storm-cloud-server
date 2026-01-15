from django.contrib import admin
from .models import APIKey, Organization, Account, EnrollmentKey


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """Admin interface for organizations."""

    list_display = ['name', 'slug', 'is_active', 'storage_quota_bytes', 'storage_used_bytes', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'slug']
    readonly_fields = ['id', 'created_at', 'updated_at', 'storage_used_bytes']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    """Admin interface for accounts."""

    list_display = ['user', 'organization', 'email_verified', 'is_owner', 'is_active', 'created_at']
    list_filter = ['is_active', 'email_verified', 'is_owner', 'organization', 'created_at']
    search_fields = ['user__username', 'user__email', 'organization__name']
    readonly_fields = ['id', 'created_at', 'updated_at', 'storage_used_bytes']

    fieldsets = (
        (None, {'fields': ('user', 'organization', 'email_verified', 'is_active')}),
        ('Action Permissions', {'fields': ('can_upload', 'can_delete', 'can_move', 'can_overwrite', 'can_create_shares', 'max_share_links', 'max_upload_bytes')}),
        ('Org Admin Permissions', {'fields': ('can_invite', 'can_manage_members', 'can_manage_api_keys', 'is_owner')}),
        ('Storage', {'fields': ('storage_quota_bytes', 'storage_used_bytes')}),
        ('Metadata', {'fields': ('id', 'created_at', 'updated_at')}),
    )


@admin.register(EnrollmentKey)
class EnrollmentKeyAdmin(admin.ModelAdmin):
    """Admin interface for enrollment keys."""

    list_display = ['name', 'organization', 'required_email', 'single_use', 'is_active', 'used_by', 'expires_at']
    list_filter = ['is_active', 'single_use', 'organization', 'created_at']
    search_fields = ['name', 'key', 'required_email', 'organization__name']
    readonly_fields = ['id', 'key', 'created_at', 'updated_at', 'used_by']


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    """Admin interface for API keys."""

    list_display = ['name', 'organization', 'created_by', 'is_active', 'created_at', 'last_used_at']
    list_filter = ['is_active', 'created_at', 'organization']
    search_fields = ['name', 'organization__name', 'created_by__user__username', 'created_by__user__email']
    readonly_fields = ['id', 'key', 'created_at', 'updated_at', 'last_used_at']

    fields = ['organization', 'created_by', 'name', 'is_active', 'permissions', 'key', 'created_at', 'updated_at', 'last_used_at']

    def get_readonly_fields(self, request, obj=None):
        """Make key and organization readonly after creation."""
        if obj:  # Editing existing object
            return self.readonly_fields + ['organization', 'created_by']
        return self.readonly_fields
