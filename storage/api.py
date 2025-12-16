"""API views for storage app."""

import uuid
from base64 import b64decode, b64encode
from pathlib import Path

from django.db.models import F
from django.http import FileResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.parsers import FileUploadParser, MultiPartParser
from rest_framework.response import Response

from core.storage.local import LocalStorageBackend
from core.throttling import (
    DownloadRateThrottle,
    PublicShareDownloadRateThrottle,
    PublicShareRateThrottle,
    UploadRateThrottle,
)
from core.utils import PathValidationError, normalize_path
from core.views import StormCloudBaseAPIView

from .models import ShareLink, StoredFile
from .serializers import (
    DirectoryListResponseSerializer,
    FileInfoResponseSerializer,
    FileListItemSerializer,
    FileUploadSerializer,
    PublicShareInfoSerializer,
    ShareLinkCreateSerializer,
    ShareLinkResponseSerializer,
    StoredFileSerializer,
)
from .utils import get_share_link_by_token


def get_user_storage_path(user) -> str:
    """Get storage path prefix for user."""
    return f"{user.id}"


class DirectoryListBaseView(StormCloudBaseAPIView):
    """Base view for listing directory contents with pagination."""

    def list_directory(self, request, dir_path=""):
        """List directory contents with pagination."""
        backend = LocalStorageBackend()
        user_prefix = get_user_storage_path(request.user)

        # Normalize and validate path
        try:
            dir_path = normalize_path(dir_path) if dir_path else ""
        except PathValidationError as e:
            return Response(
                {
                    "error": {
                        "code": "INVALID_PATH",
                        "message": str(e),
                        "path": dir_path,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Construct full storage path
        full_path = f"{user_prefix}/{dir_path}" if dir_path else user_prefix

        try:
            entries = list(backend.list(full_path))
        except FileNotFoundError:
            # Auto-create user's root directory if it doesn't exist
            if not dir_path:
                backend.mkdir(full_path)
                entries = []
            else:
                return Response(
                    {
                        "error": {
                            "code": "DIRECTORY_NOT_FOUND",
                            "message": f"Directory '{dir_path}' does not exist.",
                            "path": dir_path,
                            "recovery": "Check the path and try again.",
                        }
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
        except NotADirectoryError:
            return Response(
                {
                    "error": {
                        "code": "PATH_IS_FILE",
                        "message": f"Path '{dir_path}' is a file, not a directory.",
                        "path": dir_path,
                        "recovery": f"Use GET /api/v1/files/{dir_path}/ for file metadata.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Fetch metadata from database for entries (encryption_method + sort_position)
        entry_paths = [entry.path.replace(f"{user_prefix}/", "") for entry in entries]
        db_files = {
            f.path: {
                "encryption_method": f.encryption_method,
                "sort_position": f.sort_position,
            }
            for f in StoredFile.objects.filter(owner=request.user, path__in=entry_paths)
        }

        # Build entry data with sort_position for sorting
        entry_data = []
        for entry in entries:
            rel_path = entry.path.replace(f"{user_prefix}/", "")
            db_info = db_files.get(rel_path, {})
            entry_data.append(
                {
                    "name": entry.name,
                    "path": rel_path,
                    "size": entry.size,
                    "is_directory": entry.is_directory,
                    "content_type": entry.content_type,
                    "modified_at": entry.modified_at,
                    "encryption_method": db_info.get(
                        "encryption_method", StoredFile.ENCRYPTION_NONE
                    ),
                    "sort_position": db_info.get("sort_position"),
                }
            )

        # Sort: directories first, then by sort_position (nulls last), then alphabetically
        entry_data = sorted(
            entry_data,
            key=lambda x: (
                not x["is_directory"],
                x["sort_position"] if x["sort_position"] is not None else float("inf"),
                x["name"],
            ),
        )

        # Pagination
        limit = min(int(request.query_params.get("limit", 50)), 200)
        cursor = request.query_params.get("cursor")

        start_idx = 0
        if cursor:
            try:
                start_idx = int(b64decode(cursor).decode())
            except (ValueError, UnicodeDecodeError):
                pass

        end_idx = start_idx + limit
        page_entries = entry_data[start_idx:end_idx]

        # Generate next cursor
        next_cursor = None
        if end_idx < len(entry_data):
            next_cursor = b64encode(str(end_idx).encode()).decode()

        response_data = {
            "path": dir_path,
            "entries": page_entries,
            "count": len(page_entries),
            "total": len(entry_data),
            "next_cursor": next_cursor,
        }

        return Response(response_data)


class DirectoryListRootView(DirectoryListBaseView):
    """List root directory contents."""

    @extend_schema(
        operation_id="v1_dirs_list_root",
        summary="List root directory",
        description="List contents of the root directory. Returns files and subdirectories.",
        parameters=[
            OpenApiParameter(
                "limit", int, description="Items per page (default 50, max 200)"
            ),
            OpenApiParameter("cursor", str, description="Pagination cursor"),
        ],
        responses={
            200: DirectoryListResponseSerializer,
        },
        tags=["Files"],
    )
    def get(self, request):
        """List root directory."""
        return self.list_directory(request, dir_path="")


class DirectoryListView(DirectoryListBaseView):
    """List directory contents."""

    @extend_schema(
        operation_id="v1_dirs_list",
        summary="List directory",
        description="List contents of a specific directory. Returns files and subdirectories.",
        parameters=[
            OpenApiParameter(
                "limit", int, description="Items per page (default 50, max 200)"
            ),
            OpenApiParameter("cursor", str, description="Pagination cursor"),
        ],
        responses={
            200: DirectoryListResponseSerializer,
            404: OpenApiResponse(description="Directory not found"),
        },
        tags=["Files"],
    )
    def get(self, request, dir_path):
        """List directory contents."""
        return self.list_directory(request, dir_path)


class DirectoryCreateView(StormCloudBaseAPIView):
    """Create directory."""

    @extend_schema(
        summary="Create directory",
        description="Create a new directory. Parent directories are created as needed.",
        request=None,  # No request body needed
        responses={
            201: FileInfoResponseSerializer,
        },
        tags=["Files"],
    )
    def post(self, request, dir_path):
        """Create directory."""
        backend = LocalStorageBackend()
        user_prefix = get_user_storage_path(request.user)

        # Normalize and validate path
        try:
            dir_path = normalize_path(dir_path)
        except PathValidationError as e:
            return Response(
                {
                    "error": {
                        "code": "INVALID_PATH",
                        "message": str(e),
                        "path": dir_path,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        full_path = f"{user_prefix}/{dir_path}"

        # Check if directory already exists
        if backend.exists(full_path):
            return Response(
                {
                    "error": {
                        "code": "ALREADY_EXISTS",
                        "message": f"Directory '{dir_path}' already exists.",
                        "path": dir_path,
                    }
                },
                status=status.HTTP_409_CONFLICT,
            )

        file_info = backend.mkdir(full_path)

        # Create database record
        parent_path = str(Path(dir_path).parent) if dir_path != "." else ""

        # Shift existing files down to make room at position 0
        StoredFile.objects.filter(
            owner=request.user,
            parent_path=parent_path,
            sort_position__isnull=False,
        ).update(sort_position=F("sort_position") + 1)

        StoredFile.objects.update_or_create(
            owner=request.user,
            path=dir_path,
            defaults={
                "name": file_info.name,
                "size": 0,
                "content_type": "",
                "is_directory": True,
                "parent_path": parent_path,
                "encryption_method": StoredFile.ENCRYPTION_NONE,  # ADR 006: Default to no encryption
                "sort_position": 0,  # New directories go to top
            },
        )

        response_data = {
            "path": dir_path,
            "name": file_info.name,
            "size": 0,
            "content_type": None,
            "is_directory": True,
            "created_at": file_info.modified_at,
            "modified_at": file_info.modified_at,
            "encryption_method": StoredFile.ENCRYPTION_NONE,
        }

        return Response(response_data, status=status.HTTP_201_CREATED)


class DirectoryReorderView(StormCloudBaseAPIView):
    """Reorder files in a directory."""

    @extend_schema(
        summary="Reorder files",
        description="Set custom sort order for files in a directory. Partial list allowed.",
        request={
            "application/json": {
                "type": "object",
                "properties": {"order": {"type": "array", "items": {"type": "string"}}},
            }
        },
        responses={
            200: OpenApiResponse(description="Order updated"),
            404: OpenApiResponse(description="Directory not found"),
        },
        tags=["Files"],
    )
    def post(self, request, dir_path=""):
        """Reorder files in directory."""
        from .serializers import DirectoryReorderSerializer

        serializer = DirectoryReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.validated_data["order"]

        # Normalize path
        try:
            dir_path = normalize_path(dir_path) if dir_path else ""
        except PathValidationError as e:
            return Response(
                {
                    "error": {
                        "code": "INVALID_PATH",
                        "message": str(e),
                        "path": dir_path,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update sort_position for each file in the order list
        updated_count = 0
        for position, filename in enumerate(order):
            file_path = f"{dir_path}/{filename}" if dir_path else filename
            updated = StoredFile.objects.filter(
                owner=request.user,
                path=file_path,
            ).update(sort_position=position)
            updated_count += updated

        return Response(
            {
                "message": "Order updated",
                "path": dir_path,
                "count": updated_count,
            }
        )


class DirectoryResetOrderView(StormCloudBaseAPIView):
    """Reset file order in a directory to alphabetical."""

    @extend_schema(
        summary="Reset file order",
        description="Reset sort order to alphabetical (default) for all files in a directory.",
        request=None,
        responses={
            200: OpenApiResponse(description="Order reset"),
        },
        tags=["Files"],
    )
    def post(self, request, dir_path=""):
        """Reset file order to alphabetical."""
        # Normalize path
        try:
            dir_path = normalize_path(dir_path) if dir_path else ""
        except PathValidationError as e:
            return Response(
                {
                    "error": {
                        "code": "INVALID_PATH",
                        "message": str(e),
                        "path": dir_path,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Set sort_position to null for all files in directory
        updated = StoredFile.objects.filter(
            owner=request.user,
            parent_path=dir_path,
        ).update(sort_position=None)

        return Response(
            {
                "message": "Order reset to alphabetical",
                "path": dir_path,
                "count": updated,
            }
        )


class FileDetailView(StormCloudBaseAPIView):
    """Get file metadata."""

    @extend_schema(
        summary="Get file metadata",
        description="Returns metadata for a file. Returns 404 if path is a directory.",
        responses={
            200: FileInfoResponseSerializer,
            404: OpenApiResponse(description="File not found"),
        },
        tags=["Files"],
    )
    def get(self, request, file_path):
        """Get file metadata."""
        backend = LocalStorageBackend()
        user_prefix = get_user_storage_path(request.user)

        # Normalize and validate path
        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            return Response(
                {
                    "error": {
                        "code": "INVALID_PATH",
                        "message": str(e),
                        "path": file_path,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        full_path = f"{user_prefix}/{file_path}"

        try:
            file_info = backend.info(full_path)
        except FileNotFoundError:
            return Response(
                {
                    "error": {
                        "code": "FILE_NOT_FOUND",
                        "message": f"File '{file_path}' does not exist.",
                        "path": file_path,
                        "recovery": "Check the path and try again.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if file_info.is_directory:
            return Response(
                {
                    "error": {
                        "code": "PATH_IS_DIRECTORY",
                        "message": f"Path '{file_path}' is a directory, not a file.",
                        "path": file_path,
                        "recovery": f"Use GET /api/v1/dirs/{file_path}/ to list directory contents.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Try to get from database
        try:
            db_file = StoredFile.objects.get(owner=request.user, path=file_path)
            created_at = db_file.created_at
            encryption_method = db_file.encryption_method
        except StoredFile.DoesNotExist:
            created_at = file_info.modified_at
            encryption_method = StoredFile.ENCRYPTION_NONE

        response_data = {
            "path": file_path,
            "name": file_info.name,
            "size": file_info.size,
            "content_type": file_info.content_type,
            "is_directory": False,
            "created_at": created_at,
            "modified_at": file_info.modified_at,
            "encryption_method": encryption_method,
        }

        return Response(response_data)


class FileCreateView(StormCloudBaseAPIView):
    """Create empty file."""

    @extend_schema(
        summary="Create empty file",
        description="Create an empty file at the specified path. Parent directories are created automatically.",
        request=None,
        responses={
            201: FileInfoResponseSerializer,
            409: OpenApiResponse(description="File already exists"),
        },
        tags=["Files"],
    )
    def post(self, request, file_path):
        """Create empty file."""
        backend = LocalStorageBackend()
        user_prefix = get_user_storage_path(request.user)

        # Normalize and validate path
        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            return Response(
                {
                    "error": {
                        "code": "INVALID_PATH",
                        "message": str(e),
                        "path": file_path,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        full_path = f"{user_prefix}/{file_path}"

        # Check if file already exists
        if backend.exists(full_path):
            return Response(
                {
                    "error": {
                        "code": "ALREADY_EXISTS",
                        "message": f"File '{file_path}' already exists.",
                        "path": file_path,
                    }
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Ensure parent directory exists
        parent_path = str(Path(full_path).parent)
        if not backend.exists(parent_path):
            backend.mkdir(parent_path)

        # Create empty file
        from io import BytesIO

        empty_file = BytesIO(b"")
        file_info = backend.save(full_path, empty_file)

        # Detect content type from extension
        import mimetypes

        content_type = mimetypes.guess_type(file_path)[0] or ""

        # Create database record
        db_parent_path = str(Path(file_path).parent) if "/" in file_path else ""

        # Shift existing files down to make room at position 0
        StoredFile.objects.filter(
            owner=request.user,
            parent_path=db_parent_path,
            sort_position__isnull=False,
        ).update(sort_position=F("sort_position") + 1)

        stored_file, created = StoredFile.objects.update_or_create(
            owner=request.user,
            path=file_path,
            defaults={
                "name": file_info.name,
                "size": 0,
                "content_type": content_type,
                "is_directory": False,
                "parent_path": db_parent_path,
                "encryption_method": StoredFile.ENCRYPTION_NONE,
                "sort_position": 0,  # New files go to top
            },
        )

        response_data = {
            "path": file_path,
            "name": file_info.name,
            "size": 0,
            "content_type": content_type,
            "is_directory": False,
            "created_at": stored_file.created_at,
            "modified_at": file_info.modified_at,
            "encryption_method": stored_file.encryption_method,
        }

        return Response(response_data, status=status.HTTP_201_CREATED)


class FileUploadView(StormCloudBaseAPIView):
    """Upload file."""

    parser_classes = [MultiPartParser, FileUploadParser]
    throttle_classes = [UploadRateThrottle]

    @extend_schema(
        summary="Upload file",
        description="Upload or overwrite a file at the specified path.",
        request=FileUploadSerializer,
        responses={
            201: FileInfoResponseSerializer,
        },
        tags=["Files"],
    )
    def post(self, request, file_path):
        """Upload file."""
        if "file" not in request.FILES:
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "No file provided in request.",
                        "recovery": "Include a file in the request body with key 'file'.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        uploaded_file = request.FILES["file"]
        backend = LocalStorageBackend()
        user_prefix = get_user_storage_path(request.user)

        # Normalize and validate path
        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            return Response(
                {
                    "error": {
                        "code": "INVALID_PATH",
                        "message": str(e),
                        "path": file_path,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        full_path = f"{user_prefix}/{file_path}"

        # Ensure parent directory exists
        parent_path = str(Path(full_path).parent)
        if not backend.exists(parent_path):
            backend.mkdir(parent_path)

        # Save file
        file_info = backend.save(full_path, uploaded_file)

        # Create/update database record
        db_parent_path = str(Path(file_path).parent) if file_path != "." else ""

        # Shift existing files down to make room at position 0
        StoredFile.objects.filter(
            owner=request.user,
            parent_path=db_parent_path,
            sort_position__isnull=False,
        ).update(sort_position=F("sort_position") + 1)

        stored_file, created = StoredFile.objects.update_or_create(
            owner=request.user,
            path=file_path,
            defaults={
                "name": file_info.name,
                "size": file_info.size,
                "content_type": file_info.content_type or "",
                "is_directory": False,
                "parent_path": db_parent_path,
                "encryption_method": StoredFile.ENCRYPTION_NONE,  # ADR 006: Default to no encryption
                "sort_position": 0,  # New files go to top
            },
        )

        response_data = {
            "path": file_path,
            "name": file_info.name,
            "size": file_info.size,
            "content_type": file_info.content_type,
            "is_directory": False,
            "created_at": stored_file.created_at,
            "modified_at": file_info.modified_at,
            "encryption_method": stored_file.encryption_method,
        }

        return Response(response_data, status=status.HTTP_201_CREATED)


class FileDownloadView(StormCloudBaseAPIView):
    """Download file."""

    throttle_classes = [DownloadRateThrottle]

    @extend_schema(
        summary="Download file",
        description="Download file bytes.",
        responses={
            200: OpenApiResponse(description="File content"),
            404: OpenApiResponse(description="File not found"),
        },
        tags=["Files"],
    )
    def get(self, request, file_path):
        """Download file."""
        backend = LocalStorageBackend()
        user_prefix = get_user_storage_path(request.user)

        # Normalize and validate path
        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            return Response(
                {
                    "error": {
                        "code": "INVALID_PATH",
                        "message": str(e),
                        "path": file_path,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        full_path = f"{user_prefix}/{file_path}"

        try:
            file_handle = backend.open(full_path)
            file_info = backend.info(full_path)
        except FileNotFoundError:
            return Response(
                {
                    "error": {
                        "code": "FILE_NOT_FOUND",
                        "message": f"File '{file_path}' does not exist.",
                        "path": file_path,
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except IsADirectoryError:
            return Response(
                {
                    "error": {
                        "code": "PATH_IS_DIRECTORY",
                        "message": f"Path '{file_path}' is a directory.",
                        "path": file_path,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        response = FileResponse(file_handle)
        if file_info.content_type:
            response["Content-Type"] = file_info.content_type
        response["Content-Disposition"] = f'attachment; filename="{file_info.name}"'

        return response


class FileDeleteView(StormCloudBaseAPIView):
    """Delete file."""

    @extend_schema(
        summary="Delete file",
        description="Delete a file. Use directory endpoints for directory deletion.",
        responses={
            200: OpenApiResponse(description="File deleted successfully"),
            404: OpenApiResponse(description="File not found"),
        },
        tags=["Files"],
    )
    def delete(self, request, file_path):
        """Delete file."""
        backend = LocalStorageBackend()
        user_prefix = get_user_storage_path(request.user)

        # Normalize and validate path
        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            return Response(
                {
                    "error": {
                        "code": "INVALID_PATH",
                        "message": str(e),
                        "path": file_path,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        full_path = f"{user_prefix}/{file_path}"

        try:
            backend.delete(full_path)
        except FileNotFoundError:
            return Response(
                {
                    "error": {
                        "code": "FILE_NOT_FOUND",
                        "message": f"File '{file_path}' does not exist.",
                        "path": file_path,
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Delete from database
        StoredFile.objects.filter(owner=request.user, path=file_path).delete()

        return Response({"message": "File deleted successfully", "path": file_path})


class IndexRebuildView(StormCloudBaseAPIView):
    """Rebuild file index from filesystem (admin only)."""

    @extend_schema(
        summary="Rebuild file index",
        description="Reconcile database with filesystem. Admin only. NOT IMPLEMENTED in Phase 1.",
        request=None,
        responses={
            501: OpenApiResponse(description="Not implemented"),
        },
        tags=["Administration"],
    )
    def post(self, request):
        """Rebuild index."""
        return Response(
            {
                "error": {
                    "code": "NOT_IMPLEMENTED",
                    "message": "Index rebuild not implemented in Phase 1.",
                }
            },
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )


# =============================================================================
# Share Link Views
# =============================================================================


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
    def get(self, request):
        """List all share links for user."""
        links = (
            ShareLink.objects.filter(owner=request.user)
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
    def post(self, request):
        """Create new share link."""
        from django.conf import settings

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
            stored_file = StoredFile.objects.get(owner=request.user, path=file_path)
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
            owner=request.user,
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
    def get(self, request, share_id):
        """Get share link details."""
        try:
            link = ShareLink.objects.get(id=share_id, owner=request.user)
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
    def delete(self, request, share_id):
        """Revoke share link."""
        try:
            link = ShareLink.objects.get(id=share_id, owner=request.user)
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
    def get(self, request, token):
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
        return Response(serializer.data)


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
    def get(self, request, token):
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

        # Increment download count
        ShareLink.objects.filter(id=link.id).update(
            download_count=F("download_count") + 1, last_accessed_at=timezone.now()
        )

        # Return file response
        content_type = stored_file.content_type or "application/octet-stream"
        filename = stored_file.name
        response = FileResponse(file_handle, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
