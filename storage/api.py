"""API views for storage app."""

import uuid
from base64 import b64decode, b64encode
from io import BytesIO
from pathlib import Path
from typing import Any, Optional, Union, cast

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import F, Sum
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.parsers import FileUploadParser, MultiPartParser
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
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


def get_user_storage_path(user: User) -> str:
    """Get storage path prefix for user."""
    return f"{user.id}"


# Text MIME types allowed for content preview
TEXT_PREVIEW_MIME_TYPES: frozenset[str] = frozenset([
    # Plain text
    "text/plain",
    # Markup/Markdown
    "text/markdown",
    "text/x-markdown",
    "text/html",
    "text/xml",
    "text/css",
    # Code files
    "text/x-python",
    "text/x-python-script",
    "application/x-python-code",
    "text/javascript",
    "application/javascript",
    "application/json",
    "text/x-java-source",
    "text/x-c",
    "text/x-c++",
    "text/x-go",
    "text/x-rust",
    "text/x-ruby",
    "text/x-php",
    "text/x-sh",
    "text/x-shellscript",
    "application/x-sh",
    "text/x-yaml",
    "application/x-yaml",
    "text/x-toml",
    "application/xml",
    "application/toml",
    "text/csv",
    "text/tab-separated-values",
])

# File extensions treated as text for preview
TEXT_EXTENSIONS: frozenset[str] = frozenset([
    ".txt", ".md", ".markdown", ".rst", ".asciidoc",
    ".py", ".pyw", ".pyi",
    ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".json", ".jsonl", ".json5",
    ".html", ".htm", ".xml", ".xhtml", ".svg",
    ".css", ".scss", ".sass", ".less",
    ".java", ".kt", ".kts", ".scala",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx",
    ".go", ".rs", ".rb", ".php",
    ".sh", ".bash", ".zsh", ".fish",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".csv", ".tsv",
    ".sql", ".graphql", ".gql",
    ".env",
])

# Known filenames without extensions that are text
TEXT_FILENAMES: frozenset[str] = frozenset([
    "makefile", "dockerfile", "gemfile", "rakefile",
    "readme", "license", "changelog", "contributing",
    ".gitignore", ".dockerignore", ".editorconfig",
    ".env", ".env.example", ".env.local",
])


def is_text_file(file_path: str, content_type: Optional[str]) -> bool:
    """
    Determine if a file should be treated as text for preview.

    Uses a whitelist approach:
    1. Check content_type against known text MIME types
    2. Fall back to extension-based detection
    3. Check known text filenames without extensions
    """
    # Check MIME type first
    if content_type:
        ct_lower = content_type.lower().split(";")[0].strip()
        if ct_lower in TEXT_PREVIEW_MIME_TYPES:
            return True
        # Any text/* is allowed
        if ct_lower.startswith("text/"):
            return True

    # Check extension
    ext = Path(file_path).suffix.lower()
    if ext in TEXT_EXTENSIONS:
        return True

    # Check known filenames without extensions
    name = Path(file_path).name.lower()
    if name in TEXT_FILENAMES:
        return True

    return False


class DirectoryListBaseView(StormCloudBaseAPIView):
    """Base view for listing directory contents with pagination."""

    def list_directory(self, request: Request, dir_path: str = "") -> Response:
        """List directory contents with pagination."""
        backend = LocalStorageBackend()
        user_prefix = get_user_storage_path(cast(User, request.user))

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
    def get(self, request: Request) -> Response:
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
    def get(self, request: Request, dir_path: str) -> Response:
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
    def post(self, request: Request, dir_path: str) -> Response:
        """Create directory."""
        backend = LocalStorageBackend()
        user_prefix = get_user_storage_path(cast(User, request.user))

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
    def post(self, request: Request, dir_path: str = "") -> Response:
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
    def post(self, request: Request, dir_path: str = "") -> Response:
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
    def get(self, request: Request, file_path: str) -> Response:
        """Get file metadata."""
        backend = LocalStorageBackend()
        user_prefix = get_user_storage_path(cast(User, request.user))

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
    def post(self, request: Request, file_path: str) -> Response:
        """Create empty file."""
        backend = LocalStorageBackend()
        user_prefix = get_user_storage_path(cast(User, request.user))

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
    def post(self, request: Request, file_path: str) -> Response:
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

        # P0-3: Validate file size against global limit
        max_size = settings.STORMCLOUD_MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if uploaded_file.size > max_size:
            return Response(
                {
                    "error": {
                        "code": "FILE_TOO_LARGE",
                        "message": f"File size exceeds maximum allowed size",
                        "max_size_mb": settings.STORMCLOUD_MAX_UPLOAD_SIZE_MB,
                        "file_size_mb": round(uploaded_file.size / (1024 * 1024), 2),
                    }
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        backend = LocalStorageBackend()
        user_prefix = get_user_storage_path(cast(User, request.user))

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

        # P0-3: Validate against user quota (if set)
        # IsAuthenticated permission guarantees user is not AnonymousUser
        assert not request.user.is_anonymous
        profile = request.user.profile
        quota_bytes = profile.storage_quota_bytes
        if quota_bytes > 0:  # 0 = unlimited
            # Calculate user's current storage usage
            current_usage = (
                StoredFile.objects.filter(owner=request.user).aggregate(
                    total=Sum("size")
                )["total"]
                or 0
            )

            # For file replacement (overwrite), calculate delta instead of full size
            size_delta = uploaded_file.size
            try:
                old_file = StoredFile.objects.get(owner=request.user, path=file_path)
                size_delta = uploaded_file.size - old_file.size
            except StoredFile.DoesNotExist:
                pass  # New file, use full size

            if current_usage + size_delta > quota_bytes:
                space_needed = (current_usage + size_delta - quota_bytes) / (
                    1024 * 1024
                )
                return Response(
                    {
                        "error": {
                            "code": "QUOTA_EXCEEDED",
                            "message": "Upload would exceed your storage quota",
                            "quota_mb": round(quota_bytes / (1024 * 1024), 2),
                            "used_mb": round(current_usage / (1024 * 1024), 2),
                            "file_size_mb": round(
                                uploaded_file.size / (1024 * 1024), 2
                            ),
                            "space_needed_mb": round(space_needed, 2),
                        }
                    },
                    status=status.HTTP_507_INSUFFICIENT_STORAGE,
                )

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
    def get(self, request: Request, file_path: str) -> Union[Response, FileResponse]:
        """Download file."""
        backend = LocalStorageBackend()
        user_prefix = get_user_storage_path(cast(User, request.user))

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


class FileContentView(StormCloudBaseAPIView):
    """Preview and edit file content (text files only)."""

    throttle_classes = [DownloadRateThrottle]

    @extend_schema(
        operation_id="v1_files_content_preview",
        summary="Preview file content",
        description=(
            "Get raw text content of a file for preview. "
            "Only works for text-based files (plain text, markdown, code). "
            "Binary files will return 400 error."
        ),
        responses={
            200: OpenApiResponse(description="Raw file content (text/plain)"),
            400: OpenApiResponse(description="File is binary or path invalid"),
            404: OpenApiResponse(description="File not found"),
            413: OpenApiResponse(description="File too large for preview"),
        },
        tags=["Files"],
    )
    def get(
        self, request: Request, file_path: str
    ) -> Union[Response, HttpResponse]:
        """Preview text file content."""
        backend = LocalStorageBackend()
        user_prefix = get_user_storage_path(cast(User, request.user))

        # Validate path
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

        # Get file info
        try:
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

        # Reject directories
        if file_info.is_directory:
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

        # Check size limit
        max_preview_bytes = settings.STORMCLOUD_MAX_PREVIEW_SIZE_MB * 1024 * 1024
        if file_info.size > max_preview_bytes:
            return Response(
                {
                    "error": {
                        "code": "FILE_TOO_LARGE",
                        "message": "File exceeds maximum preview size.",
                        "max_size_mb": settings.STORMCLOUD_MAX_PREVIEW_SIZE_MB,
                        "file_size_mb": round(file_info.size / (1024 * 1024), 2),
                    }
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        # Check if text file
        if not is_text_file(file_path, file_info.content_type):
            return Response(
                {
                    "error": {
                        "code": "NOT_TEXT_FILE",
                        "message": "File is binary and cannot be previewed as text.",
                        "content_type": file_info.content_type,
                        "recovery": f"Use GET /api/v1/files/{file_path}/download/ for binary files.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Read and return content
        try:
            file_handle = backend.open(full_path)
            content = file_handle.read()
            file_handle.close()
        except Exception as e:
            return Response(
                {"error": {"code": "READ_ERROR", "message": str(e)}},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Return as plain text (not attachment download)
        response = HttpResponse(content, content_type="text/plain; charset=utf-8")
        response["X-Content-Type-Original"] = file_info.content_type or "text/plain"
        return response

    @extend_schema(
        operation_id="v1_files_content_edit",
        summary="Edit file content",
        description=(
            "Update file content with raw body. "
            "Request body contains the new file content directly (not multipart). "
            "File must already exist. Respects user storage quotas."
        ),
        request={
            "text/plain": {"schema": {"type": "string", "format": "binary"}},
            "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
        },
        responses={
            200: FileInfoResponseSerializer,
            400: OpenApiResponse(description="Invalid path or directory"),
            404: OpenApiResponse(description="File not found"),
            413: OpenApiResponse(description="Content too large"),
            507: OpenApiResponse(description="Quota exceeded"),
        },
        tags=["Files"],
    )
    def put(self, request: Request, file_path: str) -> Response:
        """Update file content."""
        backend = LocalStorageBackend()
        user_prefix = get_user_storage_path(cast(User, request.user))

        # Validate path
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

        # Check file exists (edit requires existing file)
        try:
            old_info = backend.info(full_path)
        except FileNotFoundError:
            return Response(
                {
                    "error": {
                        "code": "FILE_NOT_FOUND",
                        "message": f"File '{file_path}' does not exist.",
                        "path": file_path,
                        "recovery": "Use POST /api/v1/files/{path}/upload/ to create new files.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Reject directories
        if old_info.is_directory:
            return Response(
                {
                    "error": {
                        "code": "PATH_IS_DIRECTORY",
                        "message": "Cannot edit a directory.",
                        "path": file_path,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get request body
        content = request.body
        new_size = len(content)

        # Check global upload limit
        max_size = settings.STORMCLOUD_MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if new_size > max_size:
            return Response(
                {
                    "error": {
                        "code": "FILE_TOO_LARGE",
                        "message": "Content exceeds maximum allowed size.",
                        "max_size_mb": settings.STORMCLOUD_MAX_UPLOAD_SIZE_MB,
                        "content_size_mb": round(new_size / (1024 * 1024), 2),
                    }
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        # Check quota (calculate delta like upload does)
        profile = request.user.profile  # type: ignore[union-attr]
        quota_bytes = profile.storage_quota_bytes
        if quota_bytes > 0:
            current_usage = (
                StoredFile.objects.filter(owner=request.user).aggregate(
                    total=Sum("size")
                )["total"]
                or 0
            )
            old_size = old_info.size
            size_delta = new_size - old_size

            if current_usage + size_delta > quota_bytes:
                return Response(
                    {
                        "error": {
                            "code": "QUOTA_EXCEEDED",
                            "message": "Edit would exceed your storage quota.",
                            "quota_mb": round(quota_bytes / (1024 * 1024), 2),
                            "used_mb": round(current_usage / (1024 * 1024), 2),
                            "content_size_mb": round(new_size / (1024 * 1024), 2),
                        }
                    },
                    status=status.HTTP_507_INSUFFICIENT_STORAGE,
                )

        # Save content
        content_file = BytesIO(content)
        file_info = backend.save(full_path, content_file)

        # Update database record
        stored_file, _created = StoredFile.objects.update_or_create(
            owner=request.user,
            path=file_path,
            defaults={
                "name": file_info.name,
                "size": file_info.size,
                "content_type": file_info.content_type or "",
                "is_directory": False,
            },
        )

        # Return updated metadata
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

        return Response(response_data)


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
    def delete(self, request: Request, file_path: str) -> Response:
        """Delete file."""
        backend = LocalStorageBackend()
        user_prefix = get_user_storage_path(cast(User, request.user))

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

    permission_classes = [
        IsAdminUser
    ]  # P0-1: Admin-only for production safety (ADR 009)

    @extend_schema(
        summary="Rebuild file index",
        description="Reconcile database with filesystem. Admin only. Filesystem wins policy (ADR 000).",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["audit", "sync", "clean", "full"],
                        "default": "audit",
                        "description": "Sync mode",
                    },
                    "user_id": {
                        "type": "integer",
                        "nullable": True,
                        "description": "Specific user ID or null for all users",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "default": False,
                        "description": "Preview changes without applying",
                    },
                    "force": {
                        "type": "boolean",
                        "default": False,
                        "description": "Required for clean/full modes",
                    },
                },
            }
        },
        responses={
            200: OpenApiResponse(description="Task completed"),
            400: OpenApiResponse(description="Invalid parameters"),
        },
        tags=["Administration"],
    )
    def post(self, request: Request) -> Response:
        """Enqueue index rebuild task."""
        from storage.tasks import rebuild_storage_index

        mode = request.data.get("mode", "audit")
        user_id = request.data.get("user_id")
        dry_run = request.data.get("dry_run", False)
        force = request.data.get("force", False)

        # Validate mode
        if mode not in ["audit", "sync", "clean", "full"]:
            return Response(
                {
                    "error": {
                        "code": "INVALID_MODE",
                        "message": f"Invalid mode: {mode}",
                        "allowed": ["audit", "sync", "clean", "full"],
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate force requirement
        if mode in ["clean", "full"] and not force:
            return Response(
                {
                    "error": {
                        "code": "FORCE_REQUIRED",
                        "message": f"Mode '{mode}' requires force=true to prevent accidental data loss",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Enqueue task (ImmediateBackend completes immediately)
        result = rebuild_storage_index.enqueue(
            mode=mode,
            user_id=user_id,
            dry_run=dry_run,
            force=force,
        )

        # Return result
        return Response(
            {
                "task_id": str(result.id),
                "status": result.status,
                "result": result.return_value
                if result.status == "SUCCESSFUL"
                else None,
                "errors": [{"traceback": e.traceback} for e in result.errors]
                if result.errors
                else [],
            }
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
    def get(self, request: Request) -> Response:
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
    def post(self, request: Request) -> Response:
        """Create new share link."""
        from django.conf import settings

        from social.middleware import get_social_warnings

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
        response_data = response_serializer.data

        # Check for social posting warnings
        warnings = get_social_warnings()
        if warnings:
            response_data["warnings"] = warnings

        return Response(response_data, status=status.HTTP_201_CREATED)


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
    def delete(self, request: Request, share_id: str) -> Response:
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


# =============================================================================
# Bulk Operations Views
# =============================================================================


class BulkOperationView(StormCloudBaseAPIView):
    """Execute bulk file operations (delete, move, copy)."""

    @extend_schema(
        summary="Execute bulk operation",
        description=(
            "Perform bulk operations on multiple files/folders. "
            "Operations >50 items run asynchronously. "
            "Supports: delete, move, copy. "
            "Partial success enabled - individual failures don't abort batch."
        ),
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["delete", "move", "copy"],
                        "description": "Operation to perform",
                    },
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 250,
                        "description": "List of file/directory paths",
                    },
                    "options": {
                        "type": "object",
                        "properties": {
                            "destination": {
                                "type": "string",
                                "description": "Destination directory for move/copy",
                            }
                        },
                        "description": "Operation-specific options",
                    },
                },
                "required": ["operation", "paths"],
            }
        },
        responses={
            200: OpenApiResponse(description="Operation completed (sync)"),
            202: OpenApiResponse(description="Operation queued (async)"),
            400: OpenApiResponse(description="Validation error"),
        },
        tags=["Files"],
    )
    def post(self, request: Request) -> Response:
        """Execute bulk file operation."""
        from core.services.bulk import BulkOperationService
        from storage.serializers import (
            BulkOperationRequestSerializer,
            BulkOperationResponseSerializer,
            BulkOperationAsyncResponseSerializer,
        )

        # Validate request
        serializer = BulkOperationRequestSerializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            # Extract validation errors
            if hasattr(e, "detail"):
                error_details = e.detail
            else:
                error_details = {"detail": str(e)}

            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Invalid request data",
                        "details": error_details,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        operation = serializer.validated_data["operation"]
        paths = serializer.validated_data["paths"]
        options = serializer.validated_data.get("options", {})

        # Create service and execute
        backend = LocalStorageBackend()
        service = BulkOperationService(user=cast(User, request.user), backend=backend)

        try:
            result = service.execute(operation=operation, paths=paths, options=options)
        except ValueError as e:
            return Response(
                {"error": {"code": "INVALID_REQUEST", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if async
        if isinstance(result, dict) and result.get("async"):
            async_serializer = BulkOperationAsyncResponseSerializer(result)
            return Response(async_serializer.data, status=status.HTTP_202_ACCEPTED)
        else:
            # Sync result
            sync_serializer = BulkOperationResponseSerializer(result)
            return Response(sync_serializer.data)


class BulkStatusView(StormCloudBaseAPIView):
    """Check status of async bulk operation."""

    @extend_schema(
        summary="Check bulk operation status",
        description="Get status of an asynchronous bulk operation task",
        responses={
            200: OpenApiResponse(description="Task status"),
            403: OpenApiResponse(description="Not authorized to view this task"),
            404: OpenApiResponse(description="Task not found"),
        },
        tags=["Files"],
    )
    def get(self, request: Request, task_id: str) -> Response:
        """Get bulk operation task status."""
        from django_tasks.task import TaskResult  # type: ignore[import]
        from storage.serializers import BulkOperationStatusResponseSerializer

        # Get task result
        try:
            task_result = TaskResult.objects.get(id=task_id)  # type: ignore[attr-defined]
        except Exception:
            return Response(
                {
                    "error": {
                        "code": "TASK_NOT_FOUND",
                        "message": "Task not found",
                        "task_id": task_id,
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Verify ownership - task should have user_id in args
        # For now, we'll allow any authenticated user to check tasks
        # TODO: Add task ownership verification

        # Build response based on task status
        if task_result.status == "SUCCESSFUL":
            # Task completed
            result_data = task_result.return_value or {}
            response_data = {
                "task_id": str(task_id),
                "status": "complete",
                "operation": result_data.get("operation"),
                "total": result_data.get("total"),
                "succeeded": result_data.get("succeeded"),
                "failed": result_data.get("failed"),
                "results": result_data.get("results", []),
            }
        elif task_result.status == "FAILED":
            # Task failed
            error_msg = "Task execution failed"
            if task_result.errors:
                error_msg = (
                    str(task_result.errors[0]) if task_result.errors else error_msg
                )

            response_data = {
                "task_id": str(task_id),
                "status": "failed",
                "error": error_msg,
            }
        else:
            # Task still running (PENDING, RUNNING, etc.)
            response_data = {
                "task_id": str(task_id),
                "status": "running",
                "progress": {
                    "status": task_result.status,
                    "message": "Task is processing...",
                },
            }

        serializer = BulkOperationStatusResponseSerializer(response_data)
        return Response(serializer.data)
