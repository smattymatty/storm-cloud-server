"""API views for enrollment endpoints."""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiResponse

from core.views import StormCloudBaseAPIView
from core.throttling import AuthRateThrottle

from .models import Account, EnrollmentKey
from .enrollment_serializers import (
    TokenValidateSerializer,
    InviteDetailsSerializer,
    EnrollmentRequestSerializer,
    EnrollmentResponseSerializer,
    EnrollmentStatusSerializer,
    InviteCreateSerializer,
    InviteCreateResponseSerializer,
)
from .utils import send_verification_email
from .signals import user_registered

User = get_user_model()


class EnrollmentValidateView(StormCloudBaseAPIView):
    """Validate an enrollment token and return invite details."""

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    @extend_schema(
        summary="Validate enrollment token",
        description="Check if an enrollment token is valid and get invite details.",
        request=TokenValidateSerializer,
        responses={
            200: InviteDetailsSerializer,
            400: OpenApiResponse(description="Invalid token"),
        },
        tags=["Enrollment"],
    )
    def post(self, request: Request) -> Response:
        """Validate enrollment token."""
        serializer = TokenValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = serializer.validated_data['token']

        try:
            enrollment_key = EnrollmentKey.objects.select_related(
                'organization', 'created_by__user'
            ).get(key=token)
        except EnrollmentKey.DoesNotExist:
            return Response(
                {
                    "error": {
                        "code": "INVALID_TOKEN",
                        "message": "This enrollment token is not valid.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get server name from settings, fallback to request host
        server_name = getattr(settings, 'STORMCLOUD_SERVER_NAME', None)
        if not server_name:
            server_name = request.get_host()

        # Get inviter name
        inviter_name = None
        if enrollment_key.created_by and enrollment_key.created_by.user:
            user = enrollment_key.created_by.user
            inviter_name = user.get_full_name() or user.username

        response_data = {
            'organization_name': enrollment_key.organization.name,
            'organization_id': enrollment_key.organization.id,
            'required_email': enrollment_key.required_email,
            'expires_at': enrollment_key.expires_at,
            'is_valid': enrollment_key.is_valid(),
            'single_use': enrollment_key.single_use,
            'server_name': server_name,
            'inviter_name': inviter_name,
        }

        return Response(InviteDetailsSerializer(response_data).data)


class EnrollmentEnrollView(StormCloudBaseAPIView):
    """Create a new user account using an enrollment token."""

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    @extend_schema(
        summary="Enroll new user",
        description="Create a new user account using an enrollment token.",
        request=EnrollmentRequestSerializer,
        responses={
            201: EnrollmentResponseSerializer,
            400: OpenApiResponse(description="Validation error"),
        },
        tags=["Enrollment"],
    )
    def post(self, request: Request) -> Response:
        """Create user account with enrollment token."""
        serializer = EnrollmentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        enrollment_key = serializer.validated_data['enrollment_key']

        with transaction.atomic():
            # Create user
            user = User.objects.create_user(
                username=serializer.validated_data['username'],
                email=serializer.validated_data['email'],
                password=serializer.validated_data['password'],
            )

            # Create account in the enrollment key's organization
            account = Account.objects.create(
                user=user,
                organization=enrollment_key.organization,
                is_owner=False,  # Enrolled users are not owners
            )

            # Apply preset permissions if any
            if enrollment_key.preset_permissions:
                permission_fields = [
                    'can_upload', 'can_delete', 'can_move', 'can_overwrite',
                    'can_create_shares', 'max_share_links', 'max_upload_bytes',
                    'can_invite', 'can_manage_members', 'can_manage_api_keys',
                    'storage_quota_bytes',
                ]
                for field in permission_fields:
                    if field in enrollment_key.preset_permissions:
                        setattr(account, field, enrollment_key.preset_permissions[field])
                account.save()

            # Mark enrollment key as used
            enrollment_key.mark_used(account)

            # Fire signal
            user_registered.send(sender=User, user=user, request=request)

            # Send verification email if required
            if settings.STORMCLOUD_REQUIRE_EMAIL_VERIFICATION:
                send_verification_email(user, request)

        response_data = {
            'enrollment_id': account.id,
            'email': user.email,
            'message': 'Verification email sent. Please check your inbox.'
            if settings.STORMCLOUD_REQUIRE_EMAIL_VERIFICATION
            else 'Account created successfully.',
        }

        return Response(
            EnrollmentResponseSerializer(response_data).data,
            status=status.HTTP_201_CREATED,
        )


class EnrollmentStatusView(StormCloudBaseAPIView):
    """Check enrollment/verification status."""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Check enrollment status",
        description="Check if an enrolled user has verified their email.",
        responses={
            200: EnrollmentStatusSerializer,
            404: OpenApiResponse(description="Enrollment not found"),
        },
        tags=["Enrollment"],
    )
    def get(self, request: Request, enrollment_id: str) -> Response:
        """Get enrollment verification status."""
        account = get_object_or_404(
            Account.objects.select_related('user'),
            id=enrollment_id,
        )

        response_data = {
            'email_verified': account.email_verified,
            'can_login': account.email_verified and account.is_active,
            'email': account.user.email,
            'username': account.user.username,
        }

        return Response(EnrollmentStatusSerializer(response_data).data)


class EnrollmentResendView(StormCloudBaseAPIView):
    """Resend verification email for an enrollment."""

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    @extend_schema(
        summary="Resend verification email",
        description="Resend verification email for a pending enrollment.",
        responses={
            200: OpenApiResponse(description="Verification email sent"),
            400: OpenApiResponse(description="Already verified or rate limited"),
            404: OpenApiResponse(description="Enrollment not found"),
        },
        tags=["Enrollment"],
    )
    def post(self, request: Request, enrollment_id: str) -> Response:
        """Resend verification email."""
        account = get_object_or_404(
            Account.objects.select_related('user'),
            id=enrollment_id,
        )

        if account.email_verified:
            return Response(
                {
                    "error": {
                        "code": "ALREADY_VERIFIED",
                        "message": "This email is already verified.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Send verification email
        send_verification_email(account.user, request)

        return Response({
            'message': 'Verification email sent.',
        })


class EnrollmentInviteCreateView(StormCloudBaseAPIView):
    """Create a new enrollment invite (admin only)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Create enrollment invite",
        description="Create a new enrollment invite token. Requires can_invite permission.",
        request=InviteCreateSerializer,
        responses={
            201: InviteCreateResponseSerializer,
            403: OpenApiResponse(description="Permission denied"),
        },
        tags=["Enrollment"],
    )
    def post(self, request: Request) -> Response:
        """Create enrollment invite."""
        # Check can_invite permission
        account = request.user.account
        if not account.can_invite:
            return Response(
                {
                    "error": {
                        "code": "PERMISSION_DENIED",
                        "message": "You do not have permission to create invites.",
                        "permission": "can_invite",
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = InviteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Calculate expiry
        expiry_days = serializer.validated_data['expiry_days']
        expires_at = timezone.now() + timedelta(days=expiry_days)

        # Generate name if not provided
        name = serializer.validated_data.get('name') or ''
        if not name:
            email = serializer.validated_data.get('email')
            if email:
                name = f"Invite for {email}"
            else:
                name = f"Invite created {timezone.now().strftime('%Y-%m-%d %H:%M')}"

        # Create enrollment key
        enrollment_key = EnrollmentKey.objects.create(
            organization=account.organization,
            name=name,
            required_email=serializer.validated_data.get('email') or None,
            single_use=serializer.validated_data['single_use'],
            expires_at=expires_at,
            created_by=account,
        )

        response_data = {
            'token': enrollment_key.key,
            'expires_at': enrollment_key.expires_at,
            'required_email': enrollment_key.required_email,
            'single_use': enrollment_key.single_use,
        }

        return Response(
            InviteCreateResponseSerializer(response_data).data,
            status=status.HTTP_201_CREATED,
        )
