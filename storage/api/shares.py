"""Share link API views."""

from typing import Union

from django.db.models import F
from django.http import FileResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.permissions import check_share_link_limit, check_user_permission
from core.services.encryption import DecryptionError
from core.storage.local import LocalStorageBackend
from core.throttling import PublicShareDownloadRateThrottle, PublicShareRateThrottle
from core.views import StormCloudBaseAPIView

from storage.models import ShareLink, StoredFile
from storage.serializers import (
    PublicShareInfoSerializer,
    ShareLinkCreateSerializer,
    ShareLinkResponseSerializer,
)
from storage.services import get_user_storage_path
from storage.utils import get_share_link_by_token


class ShareLinkListCreateView(StormCloudBaseAPIView):
    """List and create share links."""

    @extend_schema(
        summary="List share links",
        description="Get all share links for the authenticated user",
        responses={
            200: ShareLinkResponseSerializer(many=True),
        },
        tags=["Share Links"],
    )
    def get(self, request: Request) -> Response:
        """List all share links for user."""
        links = (
            ShareLink.objects.filter(owner=request.user.account)
            .select_related("stored_file")
            .order_by("-created_at")
        )
        serializer = ShareLinkResponseSerializer(links, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Create share link",
        description="Create a new public share link for a file",
        request=ShareLinkCreateSerializer,
        responses={
            201: ShareLinkResponseSerializer,
            404: OpenApiResponse(description="File not found"),
            400: OpenApiResponse(description="Invalid data"),
        },
        tags=["Share Links"],
    )
    def post(self, request: Request) -> Response:
        """Create new share link."""
        from django.conf import settings

        # Check user permission to create share links
        check_user_permission(request.user, "can_create_shares")

        # Check if user has reached max share links limit
        check_share_link_limit(request.user)

        serializer = ShareLinkCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file_path = serializer.validated_data["file_path"]
        expiry_days = serializer.validated_data.get("expiry_days")
        password = serializer.validated_data.get("password")
        custom_slug = serializer.validated_data.get("custom_slug")

        # Default expiry from settings if not provided
        if expiry_days is None:
            expiry_days = getattr(settings, "STORMCLOUD_DEFAULT_SHARE_EXPIRY_DAYS", 7)

        # Check if unlimited links are allowed
        if expiry_days == 0:
            allow_unlimited = getattr(
                settings, "STORMCLOUD_ALLOW_UNLIMITED_SHARE_LINKS", True
            )
            if not allow_unlimited:
                return Response(
                    {
                        "error": {
                            "code": "UNLIMITED_NOT_ALLOWED",
                            "message": "Unlimited share links are not enabled",
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Check if file exists
        try:
            stored_file = StoredFile.objects.get(owner=request.user.account, path=file_path)
        except StoredFile.DoesNotExist:
            return Response(
                {
                    "error": {
                        "code": "FILE_NOT_FOUND",
                        "message": "File not found",
                        "path": file_path,
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Create share link
        share_link = ShareLink.objects.create(
            owner=request.user.account,
            stored_file=stored_file,
            expiry_days=expiry_days,
            custom_slug=custom_slug or None,
        )

        # Set password if provided
        if password:
            share_link.set_password(password)
            share_link.save()

        response_serializer = ShareLinkResponseSerializer(share_link)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ShareLinkDetailView(StormCloudBaseAPIView):
    """Get or revoke a share link."""

    @extend_schema(
        summary="Get share link details",
        description="Get details of a specific share link",
        responses={
            200: ShareLinkResponseSerializer,
            404: OpenApiResponse(description="Share link not found"),
        },
        tags=["Share Links"],
    )
    def get(self, request: Request, share_id: str) -> Response:
        """Get share link details."""
        try:
            link = ShareLink.objects.get(id=share_id, owner=request.user.account)
        except ShareLink.DoesNotExist:
            return Response(
                {
                    "error": {
                        "code": "LINK_NOT_FOUND",
                        "message": "Share link not found",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = ShareLinkResponseSerializer(link)
        return Response(serializer.data)

    @extend_schema(
        summary="Revoke share link",
        description="Revoke (deactivate) a share link",
        responses={
            200: OpenApiResponse(description="Link revoked"),
            404: OpenApiResponse(description="Share link not found"),
        },
        tags=["Share Links"],
    )
    def delete(self, request: Request, share_id: str) -> Response:
        """Revoke share link."""
        try:
            link = ShareLink.objects.get(id=share_id, owner=request.user.account)
        except ShareLink.DoesNotExist:
            return Response(
                {
                    "error": {
                        "code": "LINK_NOT_FOUND",
                        "message": "Share link not found",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Soft delete - set is_active=False
        link.is_active = False
        link.save(update_fields=["is_active"])

        return Response({"message": "Share link revoked", "id": str(link.id)})


class PublicShareInfoView(StormCloudBaseAPIView):
    """Get info about a public share link (no auth required)."""

    permission_classes = []  # No authentication required
    throttle_classes = [PublicShareRateThrottle]

    @extend_schema(
        summary="Get shared file info",
        description="Get information about a shared file (public, no auth required)",
        parameters=[
            OpenApiParameter(
                name="X-Share-Password",
                type=str,
                location=OpenApiParameter.HEADER,
                description="Password for protected links",
                required=False,
            )
        ],
        responses={
            200: PublicShareInfoSerializer,
            401: OpenApiResponse(description="Password required or incorrect"),
            404: OpenApiResponse(description="Link not found or expired"),
        },
        tags=["Public Share"],
    )
    def get(self, request: Request, token: str) -> Response:
        """Get shared file info."""
        # Lookup by token (UUID) or custom slug
        link = get_share_link_by_token(token)
        if not link:
            return Response(
                {
                    "error": {
                        "code": "SHARE_NOT_FOUND",
                        "message": "Share link not found or expired",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if link is valid
        if not link.is_valid():
            return Response(
                {
                    "error": {
                        "code": "SHARE_NOT_FOUND",
                        "message": "Share link not found or expired",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check password if required
        password = request.headers.get("X-Share-Password", "")
        if not link.check_password(password):
            return Response(
                {
                    "error": {
                        "code": "PASSWORD_REQUIRED"
                        if not password
                        else "INVALID_PASSWORD",
                        "message": "This link requires a password"
                        if not password
                        else "Invalid password",
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Get file info from FK (should always exist due to CASCADE)
        stored_file = link.stored_file

        # Increment view count
        ShareLink.objects.filter(id=link.id).update(
            view_count=F("view_count") + 1, last_accessed_at=timezone.now()
        )

        # Build response
        response_data = {
            "name": stored_file.name,
            "size": stored_file.size,
            "content_type": stored_file.content_type,
            "requires_password": False,  # They passed auth already
            "download_url": f"/api/v1/public/{token}/download/",
        }

        serializer = PublicShareInfoSerializer(response_data)
        response = Response(serializer.data)
        response["Cache-Control"] = "public, max-age=3600"  # 1 hour browser/CDN cache
        return response


class PublicShareDownloadView(StormCloudBaseAPIView):
    """Download a shared file (no auth required)."""

    permission_classes = []  # No authentication required
    throttle_classes = [PublicShareDownloadRateThrottle]

    @extend_schema(
        summary="Download shared file",
        description="Download a shared file (public, no auth required)",
        parameters=[
            OpenApiParameter(
                name="X-Share-Password",
                type=str,
                location=OpenApiParameter.HEADER,
                description="Password for protected links",
                required=False,
            )
        ],
        responses={
            200: OpenApiResponse(description="File download"),
            401: OpenApiResponse(description="Password required or incorrect"),
            404: OpenApiResponse(description="Link not found or expired"),
        },
        tags=["Public Share"],
    )
    def get(self, request: Request, token: str) -> Union[Response, FileResponse]:
        """Download shared file."""
        # Lookup by token (UUID) or custom slug
        link = get_share_link_by_token(token)
        if not link:
            return Response(
                {
                    "error": {
                        "code": "SHARE_NOT_FOUND",
                        "message": "Share link not found or expired",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if link is valid
        if not link.is_valid():
            return Response(
                {
                    "error": {
                        "code": "SHARE_NOT_FOUND",
                        "message": "Share link not found or expired",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check password if required
        password = request.headers.get("X-Share-Password", "")
        if not link.check_password(password):
            return Response(
                {
                    "error": {
                        "code": "PASSWORD_REQUIRED"
                        if not password
                        else "INVALID_PASSWORD",
                        "message": "This link requires a password"
                        if not password
                        else "Invalid password",
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Check if downloads are allowed
        if not link.allow_download:
            return Response(
                {
                    "error": {
                        "code": "DOWNLOAD_DISABLED",
                        "message": "Downloads are disabled for this link",
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Get file info from FK
        stored_file = link.stored_file

        # Get file from storage
        backend = LocalStorageBackend()
        user_prefix = get_user_storage_path(link.owner)
        full_path = f"{user_prefix}/{stored_file.path}"

        try:
            file_handle = backend.open(full_path)
        except FileNotFoundError:
            return Response(
                {
                    "error": {
                        "code": "FILE_NOT_FOUND",
                        "message": "File no longer exists",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except DecryptionError:
            return Response(
                {
                    "error": {
                        "code": "DECRYPTION_FAILED",
                        "message": "Unable to decrypt file",
                    }
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Increment download count
        ShareLink.objects.filter(id=link.id).update(
            download_count=F("download_count") + 1, last_accessed_at=timezone.now()
        )

        # Return file response
        content_type = stored_file.content_type or "application/octet-stream"
        filename = stored_file.name
        response = FileResponse(file_handle, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Cache-Control"] = "public, max-age=3600"  # 1 hour browser/CDN cache
        return response
