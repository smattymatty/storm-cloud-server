"""Serializers for platform-level invite and enrollment endpoints."""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Account, Organization, PlatformInvite


User = get_user_model()


class PlatformInviteCreateSerializer(serializers.Serializer):
    """Serializer for creating a platform invite (admin only)."""

    email = serializers.EmailField(
        help_text="Email address that must be used to claim this invite."
    )
    name = serializers.CharField(
        max_length=255,
        help_text="Descriptive name for this invite, e.g., 'Acme Corp Onboarding'",
    )
    quota_gb = serializers.IntegerField(
        default=0,
        min_value=0,
        help_text="Storage quota for the new org in GB. 0 = unlimited.",
    )
    expires_in_days = serializers.IntegerField(
        default=7,
        min_value=1,
        max_value=365,
        required=False,
        help_text="Days until invite expires. Default 7.",
    )


class PlatformInviteResponseSerializer(serializers.ModelSerializer):
    """Serializer for platform invite responses."""

    is_valid = serializers.SerializerMethodField()
    quota_gb = serializers.SerializerMethodField()

    class Meta:
        model = PlatformInvite
        fields = [
            "id",
            "key",
            "email",
            "name",
            "is_valid",
            "is_used",
            "quota_gb",
            "expires_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_is_valid(self, obj) -> bool:
        return obj.is_valid()

    def get_quota_gb(self, obj) -> int:
        return obj.quota_bytes // (1024 * 1024 * 1024) if obj.quota_bytes else 0


class PlatformInviteValidateSerializer(serializers.Serializer):
    """Serializer for validating a platform invite token (public)."""

    token = serializers.CharField(
        max_length=64, help_text="The platform invite token (pi_xxx)"
    )


class PlatformInviteValidateResponseSerializer(serializers.Serializer):
    """Response for invite validation."""

    email = serializers.EmailField()
    name = serializers.CharField()
    is_valid = serializers.BooleanField()
    expires_at = serializers.DateTimeField(allow_null=True)


class PlatformEnrollSerializer(serializers.Serializer):
    """Serializer for step 1: Create user account (no org yet)."""

    token = serializers.CharField(
        max_length=64, help_text="The platform invite token (pi_xxx)"
    )
    username = serializers.CharField(
        max_length=150, help_text="Username for the new account"
    )
    email = serializers.EmailField(help_text="Email address (must match invite email)")
    password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
        help_text="Password for the new account",
    )

    def validate_username(self, value):
        """Check username is unique."""
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value

    def validate_email(self, value):
        """Check email is unique."""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("This email is already registered.")
        return value.lower()

    def validate_password(self, value):
        """Validate password against Django password validators."""
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def validate(self, attrs):
        """Cross-field validation."""
        # Token validation is done in the view to provide better error messages
        return attrs


class PlatformEnrollResponseSerializer(serializers.Serializer):
    """Response for step 1: User created, needs org setup."""

    user_id = serializers.IntegerField()
    username = serializers.CharField()
    needs_org_setup = serializers.BooleanField()
    invite_name = serializers.CharField()
    quota_gb = serializers.IntegerField()


class PlatformSetupOrgSerializer(serializers.Serializer):
    """Serializer for step 2: Create organization (authenticated user)."""

    organization_name = serializers.CharField(
        max_length=255, help_text="Name for the new organization"
    )
    organization_slug = serializers.SlugField(
        max_length=255,
        required=False,
        allow_blank=True,
        help_text="Optional URL slug for organization. Auto-generated if not provided.",
    )

    def validate_organization_slug(self, value):
        """Check slug is unique if provided."""
        if value and Organization.objects.filter(slug=value).exists():
            raise serializers.ValidationError(
                "This organization slug is already taken."
            )
        return value


class PlatformSetupOrgResponseSerializer(serializers.Serializer):
    """Response for step 2: Organization and account created."""

    organization_id = serializers.UUIDField()
    organization_name = serializers.CharField()
    organization_slug = serializers.CharField()
    account_id = serializers.UUIDField()
    message = serializers.CharField()
