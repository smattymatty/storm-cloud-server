"""Serializers for enrollment API endpoints."""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import EnrollmentKey, Organization

User = get_user_model()


class TokenValidateSerializer(serializers.Serializer):
    """Input serializer for token validation."""

    token = serializers.CharField(
        max_length=64,
        help_text="Enrollment key token (e.g., ek_xxx...)"
    )


class InviteDetailsSerializer(serializers.Serializer):
    """Output serializer for invite/token details."""

    organization_name = serializers.CharField()
    organization_id = serializers.UUIDField()
    required_email = serializers.EmailField(allow_null=True)
    expires_at = serializers.DateTimeField(allow_null=True)
    is_valid = serializers.BooleanField()
    single_use = serializers.BooleanField()
    server_name = serializers.CharField()
    inviter_name = serializers.CharField(allow_null=True)


class EnrollmentRequestSerializer(serializers.Serializer):
    """Input serializer for user enrollment."""

    token = serializers.CharField(
        max_length=64,
        help_text="Enrollment key token"
    )
    username = serializers.CharField(
        max_length=150,
        help_text="Desired username"
    )
    email = serializers.EmailField(
        help_text="User's email address"
    )
    password = serializers.CharField(
        write_only=True,
        style={'input_type': 'password'},
        help_text="Password for the account"
    )

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

    def validate(self, attrs):
        """Validate token and email match requirements."""
        token = attrs.get('token')
        email = attrs.get('email')

        try:
            enrollment_key = EnrollmentKey.objects.select_related('organization').get(key=token)
        except EnrollmentKey.DoesNotExist:
            raise serializers.ValidationError({'token': 'Invalid enrollment token.'})

        if not enrollment_key.is_valid():
            raise serializers.ValidationError({'token': 'This enrollment token is no longer valid.'})

        # Check required_email if set
        if enrollment_key.required_email and enrollment_key.required_email.lower() != email.lower():
            raise serializers.ValidationError({
                'email': f'This invite is restricted to {enrollment_key.required_email}'
            })

        # Store enrollment key for use in view
        attrs['enrollment_key'] = enrollment_key
        return attrs


class EnrollmentResponseSerializer(serializers.Serializer):
    """Output serializer for successful enrollment."""

    enrollment_id = serializers.UUIDField(
        help_text="Account ID for tracking enrollment status"
    )
    email = serializers.EmailField(
        help_text="Email address to verify"
    )
    message = serializers.CharField(
        help_text="Status message"
    )


class EnrollmentStatusSerializer(serializers.Serializer):
    """Output serializer for enrollment status check."""

    email_verified = serializers.BooleanField()
    can_login = serializers.BooleanField(
        help_text="True if account is verified and active"
    )
    email = serializers.EmailField()
    username = serializers.CharField()


class InviteCreateSerializer(serializers.Serializer):
    """Input serializer for creating invite tokens (admin)."""

    email = serializers.EmailField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Optional: restrict this invite to a specific email"
    )
    expiry_days = serializers.IntegerField(
        default=7,
        min_value=1,
        max_value=365,
        help_text="Days until invite expires (1-365)"
    )
    name = serializers.CharField(
        max_length=255,
        required=False,
        default="",
        help_text="Optional descriptive name for this invite"
    )
    single_use = serializers.BooleanField(
        default=True,
        help_text="If true, invite can only be used once"
    )


class InviteCreateResponseSerializer(serializers.Serializer):
    """Output serializer for created invite."""

    token = serializers.CharField()
    expires_at = serializers.DateTimeField()
    required_email = serializers.EmailField(allow_null=True)
    single_use = serializers.BooleanField()
