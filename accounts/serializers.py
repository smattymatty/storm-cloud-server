"""Serializers for accounts app."""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from .models import APIKey, UserProfile

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Basic user serializer."""

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'date_joined', 'is_staff', 'is_superuser', 'is_active']
        read_only_fields = ['id', 'date_joined']


class UserProfileSerializer(serializers.ModelSerializer):
    """User profile serializer."""

    class Meta:
        model = UserProfile
        fields = ['is_email_verified']


class RegistrationSerializer(serializers.Serializer):
    """Serializer for user registration."""

    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})

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
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})


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
        fields = ['id', 'name', 'key', 'created_at', 'last_used_at', 'is_active']
        read_only_fields = ['id', 'key', 'created_at', 'last_used_at']


class APIKeyListSerializer(serializers.ModelSerializer):
    """Serializer for listing API keys (without the actual key)."""

    class Meta:
        model = APIKey
        fields = ['id', 'name', 'created_at', 'last_used_at', 'is_active', 'revoked_at']
        read_only_fields = fields


class APIKeyCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating API keys."""

    class Meta:
        model = APIKey
        fields = ['name']


class DeactivateAccountSerializer(serializers.Serializer):
    """Serializer for account deactivation."""

    password = serializers.CharField(write_only=True, style={'input_type': 'password'})


class DeleteAccountSerializer(serializers.Serializer):
    """Serializer for account deletion."""

    password = serializers.CharField(write_only=True, style={'input_type': 'password'})


class AuthMeResponseSerializer(serializers.Serializer):
    """Response serializer for /auth/me/ endpoint."""

    user = UserSerializer()
    profile = UserProfileSerializer()
    api_key = serializers.SerializerMethodField()

    @extend_schema_field({
        'type': 'object',
        'properties': {
            'id': {'type': 'string', 'format': 'uuid'},
            'name': {'type': 'string'},
            'last_used_at': {'type': 'string', 'format': 'date-time', 'nullable': True},
        },
        'nullable': True,
    })
    def get_api_key(self, obj):
        """Return only the ID and name of the current API key."""
        api_key = self.context.get('api_key')
        if api_key:
            return {
                'id': str(api_key.id),
                'name': api_key.name,
                'last_used_at': api_key.last_used_at,
            }
        return None


# Admin serializers
class AdminUserCreateSerializer(serializers.Serializer):
    """Serializer for admin user creation."""

    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    is_email_verified = serializers.BooleanField(default=False)
    is_staff = serializers.BooleanField(default=False)

    def validate_password(self, value):
        """Validate password."""
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
        user = self.context.get('user')
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
    profile = UserProfileSerializer()
    api_keys = APIKeyListSerializer(many=True, source='user.api_keys')
    storage_used_bytes = serializers.IntegerField(default=0)


class AdminUserQuotaUpdateSerializer(serializers.Serializer):
    """Serializer for updating user storage quota (P0-3 Security Fix)."""

    storage_quota_mb = serializers.IntegerField(
        min_value=0,
        allow_null=True,
        help_text="Storage quota in MB, or null for unlimited"
    )
