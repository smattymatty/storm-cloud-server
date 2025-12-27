"""API views for accounts app - Task 002 implementation."""

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.db.models import Count, Q
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from drf_spectacular.utils import extend_schema, OpenApiResponse

from core.views import StormCloudBaseAPIView
from core.throttling import (
    LoginRateThrottle,
    AuthRateThrottle,
    AnonLoginThrottle,
    AnonRegistrationThrottle,
)
from .models import APIKey, UserProfile, EmailVerificationToken
from .serializers import (
    UserSerializer,
    UserProfileSerializer,
    RegistrationSerializer,
    LoginSerializer,
    EmailVerificationSerializer,
    ResendVerificationSerializer,
    APIKeySerializer,
    APIKeyListSerializer,
    APIKeyCreateSerializer,
    DeactivateAccountSerializer,
    DeleteAccountSerializer,
    AuthMeResponseSerializer,
    AdminUserCreateSerializer,
    AdminUserUpdateSerializer,
    AdminPasswordResetSerializer,
    AdminUserQuotaUpdateSerializer,
)
from .signals import (
    user_registered,
    email_verified,
    api_key_created,
    api_key_revoked,
    account_deactivated,
    account_deleted,
    login_failed,
)
from .utils import get_client_ip, send_verification_email

User = get_user_model()


# =============================================================================
# Registration & Email Verification
# =============================================================================


class RegistrationView(StormCloudBaseAPIView):
    """User registration endpoint."""

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle, AnonRegistrationThrottle]

    @extend_schema(
        summary="Register new user",
        description="Create a new user account. Registration may be disabled via settings.",
        request=RegistrationSerializer,
        responses={
            201: OpenApiResponse(description="User created successfully"),
            403: OpenApiResponse(description="Registration disabled"),
            409: OpenApiResponse(description="Username or email already exists"),
        },
        tags=["Authentication"],
    )
    def post(self, request: Request) -> Response:
        """Register a new user."""
        if not settings.STORMCLOUD_ALLOW_REGISTRATION:
            return Response(
                {
                    "error": {
                        "code": "REGISTRATION_DISABLED",
                        "message": "User registration is disabled. Contact an administrator.",
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Create user
        user = User.objects.create_user(
            username=serializer.validated_data["username"],
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )

        # Create profile
        profile = UserProfile.objects.create(user=user)

        # Fire signal
        user_registered.send(sender=User, user=user, request=request)

        # Create and send verification token
        if settings.STORMCLOUD_REQUIRE_EMAIL_VERIFICATION:
            send_verification_email(user, request)

        return Response(
            {
                "user": UserSerializer(user).data,
                "message": "Verification email sent"
                if settings.STORMCLOUD_REQUIRE_EMAIL_VERIFICATION
                else "Registration successful",
                "requires_verification": settings.STORMCLOUD_REQUIRE_EMAIL_VERIFICATION,
            },
            status=status.HTTP_201_CREATED,
        )


class EmailVerificationView(StormCloudBaseAPIView):
    """Email verification endpoint."""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Verify email address",
        description="Verify user email using token sent via email.",
        request=EmailVerificationSerializer,
        responses={
            200: OpenApiResponse(description="Email verified successfully"),
            400: OpenApiResponse(description="Invalid or expired token"),
        },
        tags=["Authentication"],
    )
    def post(self, request: Request) -> Response:
        """Verify email with token."""
        serializer = EmailVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token_str = serializer.validated_data["token"]

        try:
            token = EmailVerificationToken.objects.select_related(
                "user", "user__profile"
            ).get(token=token_str)
        except EmailVerificationToken.DoesNotExist:
            return Response(
                {
                    "error": {
                        "code": "INVALID_TOKEN",
                        "message": "Verification token not found.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if token.is_expired:
            return Response(
                {
                    "error": {
                        "code": "TOKEN_EXPIRED",
                        "message": "Verification token has expired.",
                        "recovery": "Request a new verification email",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if token.used_at:
            return Response(
                {
                    "error": {
                        "code": "ALREADY_VERIFIED",
                        "message": "Email already verified.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Mark token as used
        token.mark_used()

        # Mark email as verified
        profile = token.user.profile
        profile.is_email_verified = True
        profile.save(update_fields=["is_email_verified"])

        # Fire signal
        email_verified.send(sender=User, user=token.user)

        return Response(
            {
                "message": "Email verified successfully",
                "user": UserSerializer(token.user).data,
            }
        )


class ResendVerificationView(StormCloudBaseAPIView):
    """Resend email verification."""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Resend verification email",
        description="Request a new verification email. Always returns success to prevent email enumeration.",
        request=ResendVerificationSerializer,
        responses={
            200: OpenApiResponse(
                description="Verification email sent (if account exists)"
            ),
        },
        tags=["Authentication"],
    )
    def post(self, request: Request) -> Response:
        """Resend verification email."""
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]

        # Always return success to prevent email enumeration
        try:
            user = User.objects.select_related("profile").get(email=email)
            if not user.profile.is_email_verified:
                # Send new verification email
                send_verification_email(user, request)
        except User.DoesNotExist:
            pass  # Silent fail for security

        return Response(
            {
                "message": "If an account exists with this email, a verification link has been sent"
            }
        )


# =============================================================================
# Session Login/Logout
# =============================================================================


class LoginView(StormCloudBaseAPIView):
    """Session login endpoint."""

    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle, AnonLoginThrottle]

    @extend_schema(
        summary="Login with session",
        description="Create a session cookie for Swagger UI and web testing.",
        request=LoginSerializer,
        responses={
            200: OpenApiResponse(description="Login successful"),
            401: OpenApiResponse(description="Invalid credentials"),
            403: OpenApiResponse(description="Account disabled or email not verified"),
        },
        tags=["Authentication"],
    )
    def post(self, request: Request) -> Response:
        """Login and create session."""
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        username = serializer.validated_data["username"]
        password = serializer.validated_data["password"]

        # Check if user exists and is active before authenticating
        # (Django's authenticate() returns None for inactive users)
        try:
            user_check = User.objects.get(username=username)
            if not user_check.is_active:
                login_failed.send(
                    sender=None,
                    username=username,
                    ip_address=get_client_ip(request),
                    reason="account_disabled",
                )
                return Response(
                    {
                        "error": {
                            "code": "ACCOUNT_DISABLED",
                            "message": "This account has been disabled.",
                        }
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        except User.DoesNotExist:
            pass  # Will be handled by authenticate() below

        user = authenticate(request, username=username, password=password)

        if user is None:
            # Fire failed login signal
            login_failed.send(
                sender=None,
                username=username,
                ip_address=get_client_ip(request),
                reason="invalid_credentials",
            )
            return Response(
                {
                    "error": {
                        "code": "INVALID_CREDENTIALS",
                        "message": "Invalid username or password.",
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Account is active (already checked above)
        if not user.is_active:
            login_failed.send(
                sender=None,
                username=username,
                ip_address=get_client_ip(request),
                reason="account_disabled",
            )
            return Response(
                {
                    "error": {
                        "code": "ACCOUNT_DISABLED",
                        "message": "This account has been disabled.",
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check email verification (unless admin)
        if settings.STORMCLOUD_REQUIRE_EMAIL_VERIFICATION and not user.is_staff:
            # Use select_related to avoid extra query
            user = User.objects.select_related("profile").get(pk=user.pk)
            if not user.profile.is_email_verified:
                login_failed.send(
                    sender=None,
                    username=username,
                    ip_address=get_client_ip(request),
                    reason="email_not_verified",
                )
                return Response(
                    {
                        "error": {
                            "code": "EMAIL_NOT_VERIFIED",
                            "message": "Email address not verified.",
                            "recovery": "Check your email for verification link",
                        }
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Login successful
        login(request, user)

        return Response(
            {"message": "Login successful", "user": UserSerializer(user).data}
        )


class LogoutView(StormCloudBaseAPIView):
    """Session logout endpoint."""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Logout session",
        description="Invalidate the current session cookie.",
        request=None,
        responses={
            200: OpenApiResponse(description="Logged out successfully"),
        },
        tags=["Authentication"],
    )
    def post(self, request: Request) -> Response:
        """Logout and destroy session."""
        logout(request)
        return Response({"message": "Logged out successfully"})


# =============================================================================
# API Key Management
# =============================================================================


class APIKeyCreateView(StormCloudBaseAPIView):
    """Create a new API key."""

    throttle_classes = [AuthRateThrottle]

    @extend_schema(
        summary="Generate API key",
        description="Create a new API key for CLI/programmatic access. Requires verified email unless admin.",
        request=APIKeyCreateSerializer,
        responses={
            201: APIKeySerializer,
            403: OpenApiResponse(description="Email not verified or max keys exceeded"),
        },
        tags=["Authentication"],
    )
    def post(self, request: Request) -> Response:
        """Create new API key for authenticated user."""
        # Check email verification (unless admin)
        if settings.STORMCLOUD_REQUIRE_EMAIL_VERIFICATION and not request.user.is_staff:
            profile = UserProfile.objects.get(user=request.user)
            if not profile.is_email_verified:
                return Response(
                    {
                        "error": {
                            "code": "EMAIL_NOT_VERIFIED",
                            "message": "Email address must be verified before creating API keys.",
                            "recovery": "Check your email for verification link",
                        }
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Check max keys limit
        if settings.STORMCLOUD_MAX_API_KEYS_PER_USER > 0:
            active_count = APIKey.objects.filter(
                user=request.user, is_active=True
            ).count()
            if active_count >= settings.STORMCLOUD_MAX_API_KEYS_PER_USER:
                return Response(
                    {
                        "error": {
                            "code": "MAX_KEYS_EXCEEDED",
                            "message": f"Maximum of {settings.STORMCLOUD_MAX_API_KEYS_PER_USER} active API keys allowed.",
                            "recovery": "Revoke an existing key before creating a new one",
                        }
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        serializer = APIKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Create key
        api_key = APIKey.objects.create(
            user=request.user, name=serializer.validated_data["name"]
        )

        # Fire signal
        api_key_created.send(sender=APIKey, api_key=api_key, user=request.user)

        return Response(
            {
                "id": str(api_key.id),
                "name": api_key.name,
                "key": api_key.key,
                "created_at": api_key.created_at,
                "message": "Save this key - it will not be shown again",
            },
            status=status.HTTP_201_CREATED,
        )


class APIKeyListView(StormCloudBaseAPIView):
    """List user's API keys and create new keys."""

    throttle_classes = [AuthRateThrottle]

    @extend_schema(
        summary="List API keys",
        description="Get all API keys for the authenticated user (keys themselves not included).",
        responses={
            200: OpenApiResponse(description="List of API keys"),
        },
        tags=["Authentication"],
    )
    def get(self, request: Request) -> Response:
        """List user's API keys."""
        keys = APIKey.objects.filter(user=request.user).order_by("-created_at")
        active_count = keys.filter(is_active=True).count()

        return Response(
            {
                "keys": APIKeyListSerializer(keys, many=True).data,
                "total": keys.count(),
                "active": active_count,
            }
        )

    @extend_schema(
        summary="Generate API key",
        description="Create a new API key for CLI/programmatic access. Requires verified email unless admin.",
        request=APIKeyCreateSerializer,
        responses={
            201: APIKeySerializer,
            403: OpenApiResponse(description="Email not verified or max keys exceeded"),
        },
        tags=["Authentication"],
    )
    def post(self, request: Request) -> Response:
        """Create new API key for authenticated user."""
        # Check email verification (unless admin)
        if settings.STORMCLOUD_REQUIRE_EMAIL_VERIFICATION and not request.user.is_staff:
            profile = UserProfile.objects.get(user=request.user)
            if not profile.is_email_verified:
                return Response(
                    {
                        "error": {
                            "code": "EMAIL_NOT_VERIFIED",
                            "message": "Email address must be verified before creating API keys.",
                            "recovery": "Check your email for verification link",
                        }
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Check max keys limit
        if settings.STORMCLOUD_MAX_API_KEYS_PER_USER > 0:
            active_count = APIKey.objects.filter(
                user=request.user, is_active=True
            ).count()
            if active_count >= settings.STORMCLOUD_MAX_API_KEYS_PER_USER:
                return Response(
                    {
                        "error": {
                            "code": "MAX_KEYS_EXCEEDED",
                            "message": f"Maximum of {settings.STORMCLOUD_MAX_API_KEYS_PER_USER} active API keys allowed.",
                            "recovery": "Revoke an existing key before creating a new one",
                        }
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        serializer = APIKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Create key
        api_key = APIKey.objects.create(
            user=request.user, name=serializer.validated_data["name"]
        )

        # Fire signal
        api_key_created.send(sender=APIKey, api_key=api_key, user=request.user)

        return Response(
            {
                "id": str(api_key.id),
                "name": api_key.name,
                "key": api_key.key,
                "created_at": api_key.created_at,
                "message": "Save this key - it will not be shown again",
            },
            status=status.HTTP_201_CREATED,
        )


class APIKeyRevokeView(StormCloudBaseAPIView):
    """Revoke an API key."""

    @extend_schema(
        summary="Revoke API key",
        description="Revoke an API key by ID. The key will no longer be usable.",
        request=None,
        responses={
            200: OpenApiResponse(description="Key revoked successfully"),
            404: OpenApiResponse(description="Key not found"),
            400: OpenApiResponse(description="Key already revoked"),
        },
        tags=["Authentication"],
    )
    def post(self, request: Request, key_id: int) -> Response:
        """Revoke an API key."""
        try:
            api_key = APIKey.objects.get(id=key_id, user=request.user)
        except APIKey.DoesNotExist:
            return Response(
                {
                    "error": {
                        "code": "KEY_NOT_FOUND",
                        "message": "API key not found or does not belong to you.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if not api_key.is_active:
            return Response(
                {
                    "error": {
                        "code": "ALREADY_REVOKED",
                        "message": "This API key is already revoked.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Revoke the key
        api_key.revoke()

        # Fire signal
        api_key_revoked.send(
            sender=APIKey, api_key=api_key, user=request.user, revoked_by=request.user
        )

        return Response(
            {
                "message": "API key revoked",
                "key_id": str(api_key.id),
                "key_name": api_key.name,
                "revoked_at": api_key.revoked_at,
            }
        )


# =============================================================================
# Account Management
# =============================================================================


class AuthMeView(StormCloudBaseAPIView):
    """Get current user info."""

    @extend_schema(
        summary="Get current user",
        description="Returns information about the currently authenticated user.",
        responses={
            200: AuthMeResponseSerializer,
        },
        tags=["Authentication"],
    )
    def get(self, request: Request) -> Response:
        """Get current user info."""
        profile, created = UserProfile.objects.get_or_create(user=request.user)

        data = {
            "user": request.user,
            "profile": profile,
        }

        serializer = AuthMeResponseSerializer(
            data,
            context={
                "api_key": request.auth if isinstance(request.auth, APIKey) else None
            },
        )

        return Response(serializer.data)


class DeactivateAccountView(StormCloudBaseAPIView):
    """Deactivate user account."""

    @extend_schema(
        summary="Deactivate account",
        description="Deactivate the current user's account. All API keys will be revoked.",
        request=DeactivateAccountSerializer,
        responses={
            200: OpenApiResponse(description="Account deactivated"),
            400: OpenApiResponse(description="Invalid password"),
        },
        tags=["Authentication"],
    )
    def post(self, request: Request) -> Response:
        """Deactivate account."""
        serializer = DeactivateAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Verify password
        if not request.user.check_password(serializer.validated_data["password"]):
            return Response(
                {
                    "error": {
                        "code": "INVALID_PASSWORD",
                        "message": "Password is incorrect.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Revoke all API keys
        keys_revoked = 0
        for key in APIKey.objects.filter(user=request.user, is_active=True):
            key.revoke()
            keys_revoked += 1

        # Deactivate user (IsAuthenticated permission guarantees not AnonymousUser)
        assert not request.user.is_anonymous
        request.user.is_active = False
        request.user.save(update_fields=["is_active"])

        # Fire signal
        account_deactivated.send(sender=User, user=request.user)

        # Logout
        logout(request)

        return Response(
            {"message": "Account deactivated", "keys_revoked": keys_revoked}
        )


class DeleteAccountView(StormCloudBaseAPIView):
    """Delete user account."""

    @extend_schema(
        summary="Delete account",
        description="Permanently delete the current user's account. This action cannot be undone.",
        request=DeleteAccountSerializer,
        responses={
            200: OpenApiResponse(description="Account deleted"),
            400: OpenApiResponse(description="Invalid password"),
        },
        tags=["Authentication"],
    )
    def delete(self, request: Request) -> Response:
        """Delete account."""
        serializer = DeleteAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Verify password
        if not request.user.check_password(serializer.validated_data["password"]):
            return Response(
                {
                    "error": {
                        "code": "INVALID_PASSWORD",
                        "message": "Password is incorrect.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Save user reference before logout
        user = request.user
        user_id = user.id
        username = user.username

        # Logout first
        logout(request)

        # Delete user (cascades to profile, keys, etc.)
        user.delete()

        # Fire signal
        account_deleted.send(sender=User, user_id=user_id, username=username)

        return Response({"message": "Account deleted"})


# =============================================================================
# Admin Endpoints
# =============================================================================


class AdminUserCreateView(StormCloudBaseAPIView):
    """Admin: Create a user."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Admin: Create user",
        description="Create a new user (admin only). Bypasses registration settings.",
        request=AdminUserCreateSerializer,
        responses={
            201: OpenApiResponse(description="User created"),
        },
        tags=["Administration"],
    )
    def post(self, request: Request) -> Response:
        """Create user as admin."""
        serializer = AdminUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Create user
        user = User.objects.create_user(
            username=serializer.validated_data["username"],
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
            is_staff=serializer.validated_data.get("is_staff", False),
        )

        # Create profile
        profile = UserProfile.objects.create(
            user=user,
            is_email_verified=serializer.validated_data.get("is_email_verified", False),
        )

        return Response(
            {
                "user": UserSerializer(user).data,
                "profile": UserProfileSerializer(profile).data,
                "message": "User created successfully",
            },
            status=status.HTTP_201_CREATED,
        )


class AdminUserListView(StormCloudBaseAPIView):
    """Admin: List users and create new users."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        operation_id="v1_admin_users_list",
        summary="Admin: List users",
        description="Get list of all users with filtering options. Note: Pagination deferred to Phase 3.",
        responses={
            200: OpenApiResponse(description="List of users"),
        },
        tags=["Administration"],
    )
    def get(self, request: Request) -> Response:
        """List all users.

        TODO: Add pagination in Phase 3 (DRF PageNumberPagination).
        """
        queryset = User.objects.select_related("profile").annotate(
            api_key_count=Count("api_keys")
        )

        # Filters
        is_active = request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        is_verified = request.query_params.get("is_verified")
        if is_verified is not None:
            queryset = queryset.filter(
                profile__is_email_verified=is_verified.lower() == "true"
            )

        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) | Q(email__icontains=search)
            )

        users_data = []
        for user in queryset:
            users_data.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "is_active": user.is_active,
                    "is_staff": user.is_staff,
                    "is_email_verified": user.profile.is_email_verified,
                    "date_joined": user.date_joined,
                    "api_key_count": user.api_key_count,
                }
            )

        return Response(
            {
                "users": users_data,
                "total": len(users_data),
            }
        )

    @extend_schema(
        summary="Admin: Create user",
        description="Create a new user (admin only). Bypasses registration settings.",
        request=AdminUserCreateSerializer,
        responses={
            201: OpenApiResponse(description="User created"),
        },
        tags=["Administration"],
    )
    def post(self, request: Request) -> Response:
        """Create user as admin."""
        from django.db import IntegrityError

        serializer = AdminUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            # Create user
            user = User.objects.create_user(
                username=serializer.validated_data["username"],
                email=serializer.validated_data["email"],
                password=serializer.validated_data["password"],
                is_staff=serializer.validated_data.get("is_staff", False),
                first_name=serializer.validated_data.get("first_name", ""),
                last_name=serializer.validated_data.get("last_name", ""),
            )

            # Create profile
            profile = UserProfile.objects.create(
                user=user,
                is_email_verified=serializer.validated_data.get(
                    "is_email_verified", False
                ),
            )

            return Response(
                {
                    "user": UserSerializer(user).data,
                    "profile": UserProfileSerializer(profile).data,
                    "message": "User created successfully",
                },
                status=status.HTTP_201_CREATED,
            )
        except IntegrityError as e:
            # Handle duplicate username or email
            error_msg = str(e).lower()
            if "username" in error_msg:
                field = "username"
                message = "Username already exists."
            elif "email" in error_msg:
                field = "email"
                message = "Email already exists."
            else:
                field = "unknown"
                message = "User with this information already exists."

            return Response(
                {
                    "error": {
                        "code": "ALREADY_EXISTS",
                        "message": message,
                        "field": field,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class AdminUserDetailView(StormCloudBaseAPIView):
    """Admin: Get, update, or delete user details."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        operation_id="v1_admin_users_detail",
        summary="Admin: Get user details",
        description="Get detailed information about a specific user.",
        responses={
            200: OpenApiResponse(description="User details with API keys"),
            404: OpenApiResponse(description="User not found"),
        },
        tags=["Administration"],
    )
    def get(self, request: Request, user_id: int) -> Response:
        """Get user details."""
        from django.db.models import Sum
        from storage.models import StoredFile

        try:
            user = (
                User.objects.select_related("profile")
                .prefetch_related("api_keys")
                .get(id=user_id)
            )
        except User.DoesNotExist:
            return Response(
                {
                    "error": {
                        "code": "USER_NOT_FOUND",
                        "message": "User not found.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # P0-3: Calculate storage used
        storage_used = (
            StoredFile.objects.filter(owner=user).aggregate(total=Sum("size"))["total"]
            or 0
        )

        quota_bytes = user.profile.storage_quota_bytes
        quota_mb = round(quota_bytes / (1024 * 1024), 2) if quota_bytes > 0 else None

        return Response(
            {
                "user": UserSerializer(user).data,
                "profile": UserProfileSerializer(user.profile).data,
                "api_keys": APIKeyListSerializer(user.api_keys.all(), many=True).data,
                "storage_used_bytes": storage_used,
                "storage_used_mb": round(storage_used / (1024 * 1024), 2),
                "storage_quota_mb": quota_mb,
            }
        )

    @extend_schema(
        operation_id="v1_admin_users_update",
        summary="Admin: Update user",
        description="Update user details. Username cannot be changed.",
        request=AdminUserUpdateSerializer,
        responses={
            200: OpenApiResponse(description="User updated successfully"),
            404: OpenApiResponse(description="User not found"),
            400: OpenApiResponse(description="Invalid data"),
        },
        tags=["Administration"],
    )
    def patch(self, request: Request, user_id: int) -> Response:
        """Update user details."""
        from django.db import IntegrityError

        try:
            user = User.objects.select_related("profile").get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {
                    "error": {
                        "code": "USER_NOT_FOUND",
                        "message": "User not found.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = AdminUserUpdateSerializer(
            data=request.data, context={"user": user}
        )
        serializer.is_valid(raise_exception=True)

        try:
            # Update user fields
            updated_fields = []
            if "email" in serializer.validated_data:
                user.email = serializer.validated_data["email"]
                updated_fields.append("email")
            if "first_name" in serializer.validated_data:
                user.first_name = serializer.validated_data["first_name"]
                updated_fields.append("first_name")
            if "last_name" in serializer.validated_data:
                user.last_name = serializer.validated_data["last_name"]
                updated_fields.append("last_name")
            if "is_staff" in serializer.validated_data:
                user.is_staff = serializer.validated_data["is_staff"]
                updated_fields.append("is_staff")
            if "password" in serializer.validated_data:
                user.set_password(serializer.validated_data["password"])
                updated_fields.append("password")

            if updated_fields:
                user.save(
                    update_fields=updated_fields
                    if "password" not in updated_fields
                    else None
                )

            return Response(
                {
                    "user": UserSerializer(user).data,
                    "profile": UserProfileSerializer(user.profile).data,
                    "message": "User updated successfully",
                }
            )
        except IntegrityError:
            return Response(
                {
                    "error": {
                        "code": "ALREADY_EXISTS",
                        "message": "Email already exists.",
                        "field": "email",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    @extend_schema(
        operation_id="v1_admin_users_delete",
        summary="Admin: Delete user",
        description="Permanently delete a user account. Cannot delete yourself or the last superuser.",
        responses={
            200: OpenApiResponse(description="User deleted successfully"),
            404: OpenApiResponse(description="User not found"),
            403: OpenApiResponse(
                description="Cannot delete yourself or last superuser"
            ),
        },
        tags=["Administration"],
    )
    def delete(self, request: Request, user_id: int) -> Response:
        """Delete user account."""
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {
                    "error": {
                        "code": "USER_NOT_FOUND",
                        "message": "User not found.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Prevent self-deletion
        if user.id == request.user.id:
            return Response(
                {
                    "error": {
                        "code": "CANNOT_DELETE_SELF",
                        "message": "Cannot delete your own account.",
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Prevent deletion of last superuser
        if user.is_superuser:
            superuser_count = User.objects.filter(
                is_superuser=True, is_active=True
            ).count()
            if superuser_count <= 1:
                return Response(
                    {
                        "error": {
                            "code": "LAST_SUPERUSER",
                            "message": "Cannot delete the last active superuser.",
                        }
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        username = user.username
        user.delete()

        return Response({"message": f"User '{username}' has been deleted successfully"})


class AdminUserVerifyView(StormCloudBaseAPIView):
    """Admin: Verify user email."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Admin: Verify user email",
        description="Manually verify a user's email address.",
        request=None,
        responses={
            200: OpenApiResponse(description="Email verified"),
            404: OpenApiResponse(description="User not found"),
        },
        tags=["Administration"],
    )
    def post(self, request: Request, user_id: int) -> Response:
        """Verify user email."""
        try:
            user = User.objects.select_related("profile").get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {
                    "error": {
                        "code": "USER_NOT_FOUND",
                        "message": "User not found.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        profile = user.profile
        profile.is_email_verified = True
        profile.save(update_fields=["is_email_verified"])

        return Response(
            {
                "message": "User email verified",
                "user_id": user.id,
                "username": user.username,
            }
        )


class AdminUserDeactivateView(StormCloudBaseAPIView):
    """Admin: Deactivate user."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Admin: Deactivate user",
        description="Deactivate a user's account and revoke all their API keys.",
        request=None,
        responses={
            200: OpenApiResponse(description="User deactivated"),
            404: OpenApiResponse(description="User not found"),
        },
        tags=["Administration"],
    )
    def post(self, request: Request, user_id: int) -> Response:
        """Deactivate user."""
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {
                    "error": {
                        "code": "USER_NOT_FOUND",
                        "message": "User not found.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Revoke all API keys
        keys_revoked = 0
        for key in APIKey.objects.filter(user=user, is_active=True):
            key.revoke()
            keys_revoked += 1

        # Deactivate
        user.is_active = False
        user.save(update_fields=["is_active"])

        return Response(
            {
                "message": "User deactivated",
                "user_id": user.id,
                "username": user.username,
                "keys_revoked": keys_revoked,
            }
        )


class AdminUserActivateView(StormCloudBaseAPIView):
    """Admin: Activate user."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Admin: Activate user",
        description="Reactivate a deactivated user account.",
        request=None,
        responses={
            200: OpenApiResponse(description="User activated"),
            404: OpenApiResponse(description="User not found"),
        },
        tags=["Administration"],
    )
    def post(self, request: Request, user_id: int) -> Response:
        """Activate user."""
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {
                    "error": {
                        "code": "USER_NOT_FOUND",
                        "message": "User not found.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        user.is_active = True
        user.save(update_fields=["is_active"])

        return Response(
            {"message": "User activated", "user_id": user.id, "username": user.username}
        )


class AdminUserPasswordResetView(StormCloudBaseAPIView):
    """Admin: Reset user password."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Admin: Reset user password",
        description="Reset a user's password. Requires email configuration to be implemented.",
        request=AdminPasswordResetSerializer,
        responses={
            501: OpenApiResponse(description="Not implemented - email required"),
            404: OpenApiResponse(description="User not found"),
        },
        tags=["Administration"],
    )
    def post(self, request: Request, user_id: int) -> Response:
        """Reset user password.

        P0-2 Security Fix: Endpoint blocked until email functionality is implemented.
        Returning passwords in API responses creates security risks (logging, caching, etc.)
        """
        return Response(
            {
                "error": {
                    "code": "NOT_IMPLEMENTED",
                    "message": "Password reset requires email configuration.",
                    "recovery": "Use Django management command: python manage.py changepassword <username>",
                }
            },
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )


class AdminUserQuotaUpdateView(StormCloudBaseAPIView):
    """Admin: Update user storage quota."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Admin: Update user storage quota",
        description="Set storage quota for a user in MB. Null means unlimited. P0-3 Security Fix.",
        request=AdminUserQuotaUpdateSerializer,
        responses={
            200: OpenApiResponse(description="Quota updated"),
            404: OpenApiResponse(description="User not found"),
        },
        tags=["Administration"],
    )
    def patch(self, request: Request, user_id: int) -> Response:
        """Update user quota."""
        from django.db.models import Sum
        from storage.models import StoredFile

        try:
            user = User.objects.select_related("profile").get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {
                    "error": {
                        "code": "USER_NOT_FOUND",
                        "message": "User not found.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = AdminUserQuotaUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile = user.profile
        new_quota_mb = serializer.validated_data["storage_quota_mb"]

        # Convert MB to bytes for storage (null/0 = unlimited)
        if new_quota_mb is None or new_quota_mb == 0:
            new_quota_bytes = 0  # Unlimited
        else:
            new_quota_bytes = new_quota_mb * 1024 * 1024

        # Calculate current usage
        current_usage = (
            StoredFile.objects.filter(owner=user).aggregate(total=Sum("size"))["total"]
            or 0
        )
        current_usage_mb = round(current_usage / (1024 * 1024), 2)

        # Warn if setting quota below current usage
        warning = None
        if new_quota_bytes > 0 and current_usage > new_quota_bytes:
            warning = f"User currently using {current_usage_mb}MB, which exceeds new quota of {new_quota_mb}MB. User will not be able to upload new files until they delete existing ones."

        profile.storage_quota_bytes = new_quota_bytes
        profile.save(update_fields=["storage_quota_bytes"])

        response_data = {
            "message": "Storage quota updated",
            "user_id": user.id,
            "username": user.username,
            "storage_quota_mb": new_quota_mb if new_quota_bytes > 0 else None,
            "current_usage_mb": current_usage_mb,
        }

        if warning:
            response_data["warning"] = warning

        return Response(response_data)


class AdminAPIKeyListView(StormCloudBaseAPIView):
    """Admin: List all API keys."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Admin: List all API keys",
        description="Get list of all API keys across all users. Note: Pagination deferred to Phase 3.",
        responses={
            200: OpenApiResponse(description="List of API keys"),
        },
        tags=["Administration"],
    )
    def get(self, request: Request) -> Response:
        """List all API keys.

        TODO: Add pagination in Phase 3 (DRF PageNumberPagination).
        """
        queryset = APIKey.objects.select_related("user").all()

        # Filters
        user_id = request.query_params.get("user_id")
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        is_active = request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        keys_data = []
        for key in queryset:
            keys_data.append(
                {
                    "id": str(key.id),
                    "name": key.name,
                    "user_id": key.user.id,
                    "username": key.user.username,
                    "is_active": key.is_active,
                    "created_at": key.created_at,
                    "last_used_at": key.last_used_at,
                    "revoked_at": key.revoked_at,
                }
            )

        return Response({"keys": keys_data, "total": len(keys_data)})


class AdminAPIKeyRevokeView(StormCloudBaseAPIView):
    """Admin: Revoke any API key."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Admin: Revoke API key",
        description="Revoke any user's API key.",
        request=None,
        responses={
            200: OpenApiResponse(description="Key revoked"),
            404: OpenApiResponse(description="Key not found"),
            400: OpenApiResponse(description="Key already revoked"),
        },
        tags=["Administration"],
    )
    def post(self, request: Request, key_id: int) -> Response:
        """Revoke an API key."""
        try:
            api_key = APIKey.objects.select_related("user").get(id=key_id)
        except APIKey.DoesNotExist:
            return Response(
                {
                    "error": {
                        "code": "KEY_NOT_FOUND",
                        "message": "API key not found.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if not api_key.is_active:
            return Response(
                {
                    "error": {
                        "code": "ALREADY_REVOKED",
                        "message": "This API key is already revoked.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Revoke the key
        api_key.revoke()

        # Fire signal
        api_key_revoked.send(
            sender=APIKey, api_key=api_key, user=api_key.user, revoked_by=request.user
        )

        return Response(
            {
                "message": "API key revoked",
                "key_id": str(api_key.id),
                "key_name": api_key.name,
                "user_id": api_key.user.id,
                "username": api_key.user.username,
                "revoked_at": api_key.revoked_at,
            }
        )
