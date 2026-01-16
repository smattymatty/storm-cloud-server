"""Serializers for accounts app."""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from .models import APIKey, Account, Organization, EnrollmentKey

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Basic user serializer."""

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "date_joined",
            "is_staff",
            "is_superuser",
            "is_active",
        ]
        read_only_fields = ["id", "date_joined"]


class AccountSerializer(serializers.ModelSerializer):
    """Account serializer with permission flags."""

    class Meta:
        model = Account
        fields = [
            "id",
            "email_verified",
            # Action permissions
            "can_upload",
            "can_delete",
            "can_move",
            "can_overwrite",
            "can_create_shares",
            "max_share_links",
            "max_upload_bytes",
            # Org admin permissions
            "can_invite",
            "can_manage_members",
            "can_manage_api_keys",
            "is_owner",
            # Storage
            "storage_quota_bytes",
            "storage_used_bytes",
        ]
        read_only_fields = ["id", "storage_used_bytes"]


# Backward compatibility alias
UserProfileSerializer = AccountSerializer


class RegistrationSerializer(serializers.Serializer):
    """Serializer for user registration."""

    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_password(self, value):
        """Validate password using Django's validators."""
        validate_password(value)
        return value

    def validate_username(self, value):
        """Check if username already exists."""
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already exists.")
        return value

    def validate_email(self, value):
        """Check if email already exists."""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already exists.")
        return value


class LoginSerializer(serializers.Serializer):
    """Serializer for session login."""

    username = serializers.CharField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class EmailVerificationSerializer(serializers.Serializer):
    """Serializer for email verification."""

    token = serializers.CharField()


class ResendVerificationSerializer(serializers.Serializer):
    """Serializer for resending verification email."""

    email = serializers.EmailField()


class APIKeySerializer(serializers.ModelSerializer):
    """API key serializer."""

    class Meta:
        model = APIKey
        fields = ["id", "name", "key", "created_at", "last_used_at", "is_active"]
        read_only_fields = ["id", "key", "created_at", "last_used_at"]


class APIKeyListSerializer(serializers.ModelSerializer):
    """Serializer for listing API keys (without the actual key)."""

    class Meta:
        model = APIKey
        fields = ["id", "name", "created_at", "last_used_at", "is_active", "revoked_at"]
        read_only_fields = fields


class APIKeyCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating API keys."""

    name = serializers.CharField(max_length=255, required=False, default="API Key")

    class Meta:
        model = APIKey
        fields = ["name"]


class DeactivateAccountSerializer(serializers.Serializer):
    """Serializer for account deactivation."""

    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class DeleteAccountSerializer(serializers.Serializer):
    """Serializer for account deletion."""

    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class AuthMeResponseSerializer(serializers.Serializer):
    """Response serializer for /auth/me/ endpoint."""

    user = UserSerializer()
    account = AccountSerializer()
    api_key = serializers.SerializerMethodField()

    @extend_schema_field(
        {
            "type": "object",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "name": {"type": "string"},
                "last_used_at": {
                    "type": "string",
                    "format": "date-time",
                    "nullable": True,
                },
            },
            "nullable": True,
        }
    )
    def get_api_key(self, obj):
        """Return only the ID and name of the current API key."""
        api_key = self.context.get("api_key")
        if api_key:
            return {
                "id": str(api_key.id),
                "name": api_key.name,
                "last_used_at": api_key.last_used_at,
            }
        return None


# Admin serializers
class AdminUserCreateSerializer(serializers.Serializer):
    """Serializer for admin user creation.

    Password is optional - if not provided, user will have unusable password
    and must authenticate via API key only.
    """

    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email_verified = serializers.BooleanField(default=False)
    is_staff = serializers.BooleanField(default=False)
    organization_slug = serializers.SlugField(
        required=False,
        allow_null=True,
        help_text="Organization slug. If not provided, uses admin's organization.",
    )

    def validate_password(self, value):
        """Validate password only if provided."""
        if value:
            validate_password(value)
        return value


class AdminUserUpdateSerializer(serializers.Serializer):
    """Serializer for admin user update."""

    email = serializers.EmailField(required=False)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    is_staff = serializers.BooleanField(required=False)
    password = serializers.CharField(write_only=True, required=False)

    def validate_password(self, value):
        """Validate password."""
        if value:
            validate_password(value)
        return value

    def validate_email(self, value):
        """Check if email already exists (excluding current user)."""
        user = self.context.get("user")
        if user and User.objects.filter(email=value).exclude(id=user.id).exists():
            raise serializers.ValidationError("Email already exists.")
        return value


class AdminPasswordResetSerializer(serializers.Serializer):
    """Serializer for admin password reset."""

    new_password = serializers.CharField(write_only=True, required=False)
    send_email = serializers.BooleanField(default=False)

    def validate_new_password(self, value):
        """Validate password."""
        if value:
            validate_password(value)
        return value


class AdminUserDetailSerializer(serializers.Serializer):
    """Detailed user info for admin endpoints."""

    user = UserSerializer()
    account = AccountSerializer()
    api_keys = APIKeyListSerializer(many=True, source="user.api_keys")
    storage_used_bytes = serializers.IntegerField(default=0)


class AdminUserQuotaUpdateSerializer(serializers.Serializer):
    """Serializer for updating user storage quota (P0-3 Security Fix)."""

    storage_quota_mb = serializers.IntegerField(
        min_value=0,
        allow_null=True,
        help_text="Storage quota in MB, or null for unlimited",
    )


class AdminUserPermissionsUpdateSerializer(serializers.Serializer):
    """Serializer for updating user permission flags."""

    can_upload = serializers.BooleanField(
        required=False, help_text="User can upload new files"
    )
    can_delete = serializers.BooleanField(
        required=False, help_text="User can delete files and folders"
    )
    can_move = serializers.BooleanField(
        required=False, help_text="User can move/rename files and folders"
    )
    can_overwrite = serializers.BooleanField(
        required=False, help_text="User can overwrite/edit existing files"
    )
    can_create_shares = serializers.BooleanField(
        required=False, help_text="User can create share links"
    )
    max_share_links = serializers.IntegerField(
        required=False,
        min_value=0,
        help_text="Maximum active share links allowed. 0 = unlimited",
    )
    max_upload_bytes = serializers.IntegerField(
        required=False,
        min_value=0,
        help_text="Per-file upload size limit in bytes. 0 = use server default",
    )


class AdminOrganizationSerializer(serializers.Serializer):
    """Organization info for admin list endpoint."""

    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.SlugField()
    is_active = serializers.BooleanField()
    storage_quota_bytes = serializers.IntegerField()
    storage_used_bytes = serializers.IntegerField()
    member_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()
