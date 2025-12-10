"""API views for accounts app."""

from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema, OpenApiResponse

from core.views import StormCloudBaseAPIView
from .models import APIKey
from .serializers import (
    APIKeySerializer,
    APIKeyCreateSerializer,
    AuthMeResponseSerializer,
    UserSerializer,
)


class AuthTokenCreateView(StormCloudBaseAPIView):
    """Create a new API key for the authenticated user."""
    permission_classes = [AllowAny]  # TODO: Phase 1 allows creation, lock down later

    @extend_schema(
        summary="Create API key",
        description="Create a new API key for authentication. For Phase 1, requires admin to create via admin panel first.",
        request=APIKeyCreateSerializer,
        responses={
            201: APIKeySerializer,
        },
        tags=['Authentication']
    )
    def post(self, request):
        """Create new API key."""
        serializer = APIKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # TODO: Phase 1 - This endpoint is a stub. API keys created via admin panel.
        # In production, this would require authentication and create the key.
        return Response(
            {
                "error": {
                    "code": "NOT_IMPLEMENTED",
                    "message": "API key creation via API not implemented in Phase 1.",
                    "recovery": "Create API keys via Django admin panel at /admin/"
                }
            },
            status=status.HTTP_501_NOT_IMPLEMENTED
        )


class AuthTokenRevokeView(StormCloudBaseAPIView):
    """Revoke the current API key."""

    @extend_schema(
        summary="Revoke API key",
        description="Revoke the current API key. The key will be deactivated and cannot be used for future requests.",
        responses={
            200: OpenApiResponse(description="API key revoked successfully"),
        },
        tags=['Authentication']
    )
    def post(self, request):
        """Revoke current API key."""
        api_key = request.auth

        if isinstance(api_key, APIKey):
            api_key.is_active = False
            api_key.save(update_fields=['is_active'])

            return Response({
                "message": "API key revoked successfully",
                "key_name": api_key.name
            })

        return Response(
            {
                "error": {
                    "code": "INVALID_AUTH",
                    "message": "No API key found in request"
                }
            },
            status=status.HTTP_400_BAD_REQUEST
        )


class AuthMeView(StormCloudBaseAPIView):
    """Get information about the current authenticated user."""

    @extend_schema(
        summary="Get current user",
        description="Returns information about the currently authenticated user and their API key.",
        responses={
            200: AuthMeResponseSerializer,
        },
        tags=['Authentication']
    )
    def get(self, request):
        """Get current user info."""
        data = {
            'user': request.user,
        }

        serializer = AuthMeResponseSerializer(
            data,
            context={'api_key': request.auth if isinstance(request.auth, APIKey) else None}
        )

        return Response(serializer.data)
