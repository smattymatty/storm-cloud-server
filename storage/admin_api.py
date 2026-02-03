"""Admin API views for file operations on user files.

These endpoints allow admins to browse and manage any user's files
while maintaining a complete audit trail.
"""

from base64 import b64decode, b64encode
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union, cast

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.db.models.functions import Lower
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FileUploadParser, MultiPartParser
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response

from core.services.bulk import BulkOperationService
from core.services.encryption import DecryptionError
from core.storage.local import LocalStorageBackend
from core.utils import PathValidationError, normalize_path
from core.views import StormCloudBaseAPIView

from .services import generate_etag, is_text_file
from .models import FileAuditLog, StoredFile
from .serializers import FileAuditLogSerializer
from .signals import file_action_performed

if TYPE_CHECKING:
    from accounts.typing import UserProtocol as User
else:
    User = get_user_model()


def get_target_user_storage_path(target_user: User) -> str:
    """Get storage path prefix for target user (Account UUID)."""
    return f"{target_user.account.id}"


def emit_admin_file_action(
    sender: Any,
    request: Request,
    target_user: User,
    action: str,
    path: str,
    success: bool = True,
    **kwargs: Any,
) -> None:
    """Emit file action signal for admin operations."""
    file_action_performed.send(
        sender=sender,
        performed_by=request.user,
        target_user=target_user,
        is_admin_action=True,
        action=action,
        path=path,
        success=success,
        request=request,
        **kwargs,
    )


class AdminFileBaseView(StormCloudBaseAPIView):
    """Base view for admin file operations on user's files."""

    permission_classes = [IsAdminUser]

    def get_target_user(self, user_id: int) -> User:
        """Get the target user whose files we're operating on."""
        return get_object_or_404(User, pk=user_id)


# =============================================================================
# Directory Views
# =============================================================================


class AdminDirectoryListRootView(AdminFileBaseView):
    """List a user's root directory (admin)."""

    @extend_schema(
        summary="List user's root directory (Admin)",
        description="List contents of a user's root storage directory.",
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                location=OpenApiParameter.PATH,
                description="Target user ID",
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Max entries per page (default 50, max 200)",
            ),
            OpenApiParameter(
                name="cursor",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Pagination cursor",
            ),
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter by name (case-insensitive contains)",
            ),
        ],
        responses={200: OpenApiResponse(description="Directory listing")},
        tags=["Admin - Files"],
    )
    def get(self, request: Request, user_id: int) -> Response:
        """List user's root directory."""
        target_user = self.get_target_user(user_id)
        return self._list_directory(request, target_user, "")

    def _list_directory(
        self, request: Request, target_user: User, dir_path: str
    ) -> Response:
        """List directory contents with pagination."""
        backend = LocalStorageBackend()
        user_prefix = get_target_user_storage_path(target_user)

        # Normalize and validate path
        try:
            dir_path = normalize_path(dir_path) if dir_path else ""
        except PathValidationError as e:
            emit_admin_file_action(
                self.__class__,
                request,
                target_user,
                FileAuditLog.ACTION_LIST,
                dir_path,
                success=False,
                error_code="INVALID_PATH",
                error_message=str(e),
            )
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

        full_path = f"{user_prefix}/{dir_path}" if dir_path else user_prefix

        try:
            entries = list(backend.list(full_path))
        except FileNotFoundError:
            if not dir_path:
                backend.mkdir(full_path)
                entries = []
            else:
                emit_admin_file_action(
                    self.__class__,
                    request,
                    target_user,
                    FileAuditLog.ACTION_LIST,
                    dir_path,
                    success=False,
                    error_code="DIRECTORY_NOT_FOUND",
                )
                return Response(
                    {
                        "error": {
                            "code": "DIRECTORY_NOT_FOUND",
                            "message": f"Directory '{dir_path}' does not exist.",
                            "path": dir_path,
                        }
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
        except NotADirectoryError:
            emit_admin_file_action(
                self.__class__,
                request,
                target_user,
                FileAuditLog.ACTION_LIST,
                dir_path,
                success=False,
                error_code="PATH_IS_FILE",
            )
            return Response(
                {
                    "error": {
                        "code": "PATH_IS_FILE",
                        "message": f"Path '{dir_path}' is a file, not a directory.",
                        "path": dir_path,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Fetch metadata from database
        entry_paths = [entry.path.replace(f"{user_prefix}/", "") for entry in entries]
        db_files = {
            f.path: {
                "encryption_method": f.encryption_method,
                "sort_position": f.sort_position,
            }
            for f in StoredFile.objects.filter(
                owner=target_user.account, path__in=entry_paths
            )
        }

        # Build entry data
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

        # Sort: directories first, then by sort_position, then alphabetically
        entry_data = sorted(
            entry_data,
            key=lambda x: (
                not x["is_directory"],
                x["sort_position"] if x["sort_position"] is not None else float("inf"),
                x["name"],
            ),
        )

        # Filter by search term
        search = request.query_params.get("search", "").strip()
        if search:
            search_lower = search.lower()
            entry_data = [
                e for e in entry_data if search_lower in str(e["name"]).lower()
            ]

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

        next_cursor = None
        if end_idx < len(entry_data):
            next_cursor = b64encode(str(end_idx).encode()).decode()

        # Log successful list
        emit_admin_file_action(
            self.__class__,
            request,
            target_user,
            FileAuditLog.ACTION_LIST,
            dir_path or "/",
            success=True,
        )

        return Response(
            {
                "path": dir_path,
                "target_user": {"id": target_user.id, "username": target_user.username},
                "entries": page_entries,
                "count": len(page_entries),
                "total": len(entry_data),
                "next_cursor": next_cursor,
            }
        )


class AdminDirectoryListView(AdminDirectoryListRootView):
    """List a user's subdirectory (admin)."""

    @extend_schema(
        summary="List user's directory (Admin)",
        description="List contents of a specific directory in user's storage.",
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                location=OpenApiParameter.PATH,
                description="Target user ID",
            ),
            OpenApiParameter(
                name="dir_path",
                type=str,
                location=OpenApiParameter.PATH,
                description="Directory path",
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Max entries per page (default 50, max 200)",
            ),
            OpenApiParameter(
                name="cursor",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Pagination cursor",
            ),
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter by name (case-insensitive contains)",
            ),
        ],
        responses={200: OpenApiResponse(description="Directory listing")},
        tags=["Admin - Files"],
    )
    def get(self, request: Request, user_id: int, dir_path: str) -> Response:
        """List user's directory."""
        target_user = self.get_target_user(user_id)
        return self._list_directory(request, target_user, dir_path)


class AdminDirectoryCreateView(AdminFileBaseView):
    """Create directory in user's storage (admin)."""

    @extend_schema(
        summary="Create directory for user (Admin)",
        description="Create a new directory in user's storage.",
        responses={201: OpenApiResponse(description="Directory created")},
        tags=["Admin - Files"],
    )
    def post(self, request: Request, user_id: int, dir_path: str) -> Response:
        """Create directory."""
        target_user = self.get_target_user(user_id)
        backend = LocalStorageBackend()
        user_prefix = get_target_user_storage_path(target_user)

        try:
            dir_path = normalize_path(dir_path)
        except PathValidationError as e:
            emit_admin_file_action(
                self.__class__,
                request,
                target_user,
                FileAuditLog.ACTION_CREATE_DIR,
                dir_path,
                success=False,
                error_code="INVALID_PATH",
                error_message=str(e),
            )
            return Response(
                {"error": {"code": "INVALID_PATH", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        full_path = f"{user_prefix}/{dir_path}"

        # Check if exists on filesystem OR in database
        if (
            backend.exists(full_path)
            or StoredFile.objects.filter(
                owner=target_user.account, path=dir_path
            ).exists()
        ):
            emit_admin_file_action(
                self.__class__,
                request,
                target_user,
                FileAuditLog.ACTION_CREATE_DIR,
                dir_path,
                success=False,
                error_code="ALREADY_EXISTS",
            )
            return Response(
                {
                    "error": {
                        "code": "ALREADY_EXISTS",
                        "message": f"Path '{dir_path}' already exists.",
                    }
                },
                status=status.HTTP_409_CONFLICT,
            )

        backend.mkdir(full_path)

        # Create database record (use get_or_create for safety)
        parent_path = str(Path(dir_path).parent) if "/" in dir_path else ""
        StoredFile.objects.get_or_create(
            owner=target_user.account,
            path=dir_path,
            defaults={
                "name": Path(dir_path).name,
                "size": 0,
                "content_type": "",
                "is_directory": True,
                "parent_path": parent_path,
                "encryption_method": StoredFile.ENCRYPTION_NONE,
            },
        )

        emit_admin_file_action(
            self.__class__,
            request,
            target_user,
            FileAuditLog.ACTION_CREATE_DIR,
            dir_path,
            success=True,
        )

        return Response(
            {
                "path": dir_path,
                "is_directory": True,
                "target_user": {"id": target_user.id, "username": target_user.username},
            },
            status=status.HTTP_201_CREATED,
        )


# =============================================================================
# File Views
# =============================================================================


class AdminFileDetailView(AdminFileBaseView):
    """Get file metadata for user's file (admin)."""

    @extend_schema(
        summary="Get user's file metadata (Admin)",
        description="Get metadata for a file in user's storage.",
        responses={200: OpenApiResponse(description="File metadata")},
        tags=["Admin - Files"],
    )
    def get(self, request: Request, user_id: int, file_path: str) -> Response:
        """Get file metadata."""
        target_user = self.get_target_user(user_id)
        backend = LocalStorageBackend()
        user_prefix = get_target_user_storage_path(target_user)

        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            return Response(
                {"error": {"code": "INVALID_PATH", "message": str(e)}},
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
                        "message": f"File '{file_path}' not found.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get database record for encryption info
        try:
            db_file = StoredFile.objects.get(owner=target_user.account, path=file_path)
            encryption_method = db_file.encryption_method
            created_at = db_file.created_at
        except StoredFile.DoesNotExist:
            encryption_method = StoredFile.ENCRYPTION_NONE
            created_at = file_info.modified_at

        etag = generate_etag(file_path, file_info.size, file_info.modified_at)

        response_data = {
            "path": file_path,
            "name": file_info.name,
            "size": file_info.size,
            "content_type": file_info.content_type,
            "is_directory": file_info.is_directory,
            "created_at": created_at,
            "modified_at": file_info.modified_at,
            "encryption_method": encryption_method,
            "etag": etag,
            "target_user": {"id": target_user.id, "username": target_user.username},
        }

        response = Response(response_data)
        response["ETag"] = f'"{etag}"'
        return response


class AdminFileUploadView(AdminFileBaseView):
    """Upload file to user's storage (admin)."""

    parser_classes = [MultiPartParser, FileUploadParser]

    @extend_schema(
        summary="Upload file for user (Admin)",
        description="Upload a file to user's storage.",
        responses={201: OpenApiResponse(description="File uploaded")},
        tags=["Admin - Files"],
    )
    def post(self, request: Request, user_id: int, file_path: str) -> Response:
        """Upload file."""
        target_user = self.get_target_user(user_id)

        if "file" not in request.FILES:
            return Response(
                {"error": {"code": "VALIDATION_ERROR", "message": "No file provided."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        uploaded_file = request.FILES["file"]

        # Check global file size limit
        max_size = settings.STORMCLOUD_MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if uploaded_file.size > max_size:
            emit_admin_file_action(
                self.__class__,
                request,
                target_user,
                FileAuditLog.ACTION_UPLOAD,
                file_path,
                success=False,
                error_code="FILE_TOO_LARGE",
            )
            return Response(
                {
                    "error": {
                        "code": "FILE_TOO_LARGE",
                        "message": "File size exceeds maximum allowed size",
                        "max_size_mb": settings.STORMCLOUD_MAX_UPLOAD_SIZE_MB,
                    }
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        backend = LocalStorageBackend()
        user_prefix = get_target_user_storage_path(target_user)

        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            emit_admin_file_action(
                self.__class__,
                request,
                target_user,
                FileAuditLog.ACTION_UPLOAD,
                file_path,
                success=False,
                error_code="INVALID_PATH",
                error_message=str(e),
            )
            return Response(
                {"error": {"code": "INVALID_PATH", "message": str(e)}},
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
        db_parent_path = str(Path(file_path).parent) if "/" in file_path else ""

        stored_file, created = StoredFile.objects.update_or_create(
            owner=target_user.account,
            path=file_path,
            defaults={
                "name": file_info.name,
                "size": file_info.size,
                "content_type": file_info.content_type or "",
                "is_directory": False,
                "parent_path": db_parent_path,
                "encryption_method": file_info.encryption_method,
                "key_id": file_info.encryption_key_id,
                "encrypted_size": file_info.encrypted_size,
            },
        )

        emit_admin_file_action(
            self.__class__,
            request,
            target_user,
            FileAuditLog.ACTION_UPLOAD,
            file_path,
            success=True,
            file_size=file_info.size,
            content_type=file_info.content_type,
        )

        return Response(
            {
                "path": file_path,
                "name": file_info.name,
                "size": file_info.size,
                "content_type": file_info.content_type,
                "is_directory": False,
                "created_at": stored_file.created_at,
                "modified_at": file_info.modified_at,
                "target_user": {"id": target_user.id, "username": target_user.username},
            },
            status=status.HTTP_201_CREATED,
        )


class AdminFileCreateView(AdminFileBaseView):
    """Create empty file in user's storage (admin)."""

    @extend_schema(
        summary="Create empty file for user (Admin)",
        description="Create a new empty file in user's storage.",
        responses={201: OpenApiResponse(description="File created")},
        tags=["Admin - Files"],
    )
    def post(self, request: Request, user_id: int, file_path: str) -> Response:
        """Create empty file."""
        target_user = self.get_target_user(user_id)
        backend = LocalStorageBackend()
        user_prefix = get_target_user_storage_path(target_user)

        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            emit_admin_file_action(
                self.__class__,
                request,
                target_user,
                FileAuditLog.ACTION_UPLOAD,
                file_path,
                success=False,
                error_code="INVALID_PATH",
                error_message=str(e),
            )
            return Response(
                {"error": {"code": "INVALID_PATH", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        full_path = f"{user_prefix}/{file_path}"

        # Check if already exists
        if backend.exists(full_path):
            emit_admin_file_action(
                self.__class__,
                request,
                target_user,
                FileAuditLog.ACTION_UPLOAD,
                file_path,
                success=False,
                error_code="ALREADY_EXISTS",
            )
            return Response(
                {
                    "error": {
                        "code": "ALREADY_EXISTS",
                        "message": f"File '{file_path}' already exists.",
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
        empty_file.name = Path(file_path).name
        file_info = backend.save(full_path, empty_file)

        # Determine content type from extension
        import mimetypes

        content_type = mimetypes.guess_type(file_path)[0] or "text/plain"

        # Create database record
        db_parent_path = str(Path(file_path).parent) if "/" in file_path else ""
        stored_file = StoredFile.objects.create(
            owner=target_user.account,
            path=file_path,
            name=Path(file_path).name,
            size=file_info.size,
            content_type=content_type,
            is_directory=False,
            parent_path=db_parent_path,
            encryption_method=file_info.encryption_method,
            key_id=file_info.encryption_key_id,
            encrypted_size=file_info.encrypted_size,
        )

        emit_admin_file_action(
            self.__class__,
            request,
            target_user,
            FileAuditLog.ACTION_UPLOAD,
            file_path,
            success=True,
            file_size=0,
            content_type=content_type,
        )

        return Response(
            {
                "detail": "File created",
                "path": file_path,
                "name": stored_file.name,
                "size": file_info.size,
                "content_type": content_type,
                "is_directory": False,
                "created_at": stored_file.created_at,
                "modified_at": file_info.modified_at,
                "encryption_method": stored_file.encryption_method,
                "target_user": {"id": target_user.id, "username": target_user.username},
            },
            status=status.HTTP_201_CREATED,
        )


class AdminFileDownloadView(AdminFileBaseView):
    """Download file from user's storage (admin)."""

    @extend_schema(
        summary="Download user's file (Admin)",
        description="Download a file from user's storage.",
        responses={200: OpenApiResponse(description="File content")},
        tags=["Admin - Files"],
    )
    def get(
        self, request: Request, user_id: int, file_path: str
    ) -> Union[Response, FileResponse]:
        """Download file."""
        target_user = self.get_target_user(user_id)
        backend = LocalStorageBackend()
        user_prefix = get_target_user_storage_path(target_user)

        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            return Response(
                {"error": {"code": "INVALID_PATH", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        full_path = f"{user_prefix}/{file_path}"

        try:
            file_info = backend.info(full_path)
        except FileNotFoundError:
            emit_admin_file_action(
                self.__class__,
                request,
                target_user,
                FileAuditLog.ACTION_DOWNLOAD,
                file_path,
                success=False,
                error_code="FILE_NOT_FOUND",
            )
            return Response(
                {
                    "error": {
                        "code": "FILE_NOT_FOUND",
                        "message": f"File '{file_path}' not found.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if file_info.is_directory:
            return Response(
                {
                    "error": {
                        "code": "PATH_IS_DIRECTORY",
                        "message": "Cannot download a directory.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ETag support
        etag = generate_etag(file_path, file_info.size, file_info.modified_at)
        if_none_match = request.headers.get("If-None-Match", "").strip('"')
        if if_none_match == etag:
            response = HttpResponse(status=304)
            response["ETag"] = f'"{etag}"'
            return response

        try:
            file_handle = backend.open(full_path)
        except DecryptionError:
            emit_admin_file_action(
                self.__class__,
                request,
                target_user,
                FileAuditLog.ACTION_DOWNLOAD,
                file_path,
                success=False,
                error_code="DECRYPTION_FAILED",
                error_message="Unable to decrypt file",
            )
            return Response(
                {
                    "error": {
                        "code": "DECRYPTION_FAILED",
                        "message": "Unable to decrypt file",
                        "path": file_path,
                    }
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        emit_admin_file_action(
            self.__class__,
            request,
            target_user,
            FileAuditLog.ACTION_DOWNLOAD,
            file_path,
            success=True,
            file_size=file_info.size,
            content_type=file_info.content_type,
        )

        response = FileResponse(file_handle)
        response["ETag"] = f'"{etag}"'
        response["Cache-Control"] = "private, must-revalidate"
        if file_info.content_type:
            response["Content-Type"] = file_info.content_type
        response["Content-Disposition"] = f'attachment; filename="{file_info.name}"'

        return response


class AdminFileDeleteView(AdminFileBaseView):
    """Delete file from user's storage (admin)."""

    @extend_schema(
        summary="Delete user's file (Admin)",
        description="Delete a file or directory from user's storage.",
        responses={204: OpenApiResponse(description="File deleted")},
        tags=["Admin - Files"],
    )
    def delete(self, request: Request, user_id: int, file_path: str) -> Response:
        """Delete file."""
        target_user = self.get_target_user(user_id)
        backend = LocalStorageBackend()
        user_prefix = get_target_user_storage_path(target_user)

        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            emit_admin_file_action(
                self.__class__,
                request,
                target_user,
                FileAuditLog.ACTION_DELETE,
                file_path,
                success=False,
                error_code="INVALID_PATH",
            )
            return Response(
                {"error": {"code": "INVALID_PATH", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        full_path = f"{user_prefix}/{file_path}"

        try:
            file_info = backend.info(full_path)
        except FileNotFoundError:
            emit_admin_file_action(
                self.__class__,
                request,
                target_user,
                FileAuditLog.ACTION_DELETE,
                file_path,
                success=False,
                error_code="FILE_NOT_FOUND",
            )
            return Response(
                {
                    "error": {
                        "code": "FILE_NOT_FOUND",
                        "message": f"File '{file_path}' not found.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Delete from filesystem
        if file_info.is_directory:
            # Use fd-pinned safe_rmtree for recursive directory deletion
            from core.utils import safe_rmtree

            resolved_path = backend._resolve_path(full_path)
            safe_rmtree(resolved_path, backend.storage_root)
        else:
            backend.delete(full_path)

        # Delete database record (CASCADE will handle ShareLinks)
        StoredFile.objects.filter(owner=target_user.account, path=file_path).delete()

        # For directories, also delete child records
        if file_info.is_directory:
            StoredFile.objects.filter(
                owner=target_user.account, path__startswith=f"{file_path}/"
            ).delete()

        emit_admin_file_action(
            self.__class__,
            request,
            target_user,
            FileAuditLog.ACTION_DELETE,
            file_path,
            success=True,
        )

        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminFileContentView(AdminFileBaseView):
    """Preview/edit text file content for user (admin)."""

    @extend_schema(
        summary="Preview user's file content (Admin)",
        description="Get text content of a file in user's storage.",
        responses={200: OpenApiResponse(description="File content as text")},
        tags=["Admin - Files"],
    )
    def get(self, request: Request, user_id: int, file_path: str) -> Response:
        """Preview file content."""
        target_user = self.get_target_user(user_id)
        backend = LocalStorageBackend()
        user_prefix = get_target_user_storage_path(target_user)

        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            return Response(
                {"error": {"code": "INVALID_PATH", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        full_path = f"{user_prefix}/{file_path}"

        try:
            file_info = backend.info(full_path)
        except FileNotFoundError:
            emit_admin_file_action(
                self.__class__,
                request,
                target_user,
                FileAuditLog.ACTION_PREVIEW,
                file_path,
                success=False,
                error_code="FILE_NOT_FOUND",
            )
            return Response(
                {
                    "error": {
                        "code": "FILE_NOT_FOUND",
                        "message": f"File '{file_path}' not found.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if file_info.is_directory:
            return Response(
                {
                    "error": {
                        "code": "PATH_IS_DIRECTORY",
                        "message": "Cannot preview a directory.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not is_text_file(file_info.name, file_info.content_type):
            emit_admin_file_action(
                self.__class__,
                request,
                target_user,
                FileAuditLog.ACTION_PREVIEW,
                file_path,
                success=False,
                error_code="NOT_TEXT_FILE",
            )
            return Response(
                {
                    "error": {
                        "code": "NOT_TEXT_FILE",
                        "message": "File is not a text file.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        max_preview_size = (
            getattr(settings, "STORMCLOUD_MAX_PREVIEW_SIZE_MB", 5) * 1024 * 1024
        )
        if file_info.size > max_preview_size:
            return Response(
                {
                    "error": {
                        "code": "FILE_TOO_LARGE",
                        "message": "File too large for preview.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with backend.open(full_path) as f:
                raw_content = f.read()
                content: str = (
                    raw_content.decode("utf-8", errors="replace")
                    if isinstance(raw_content, bytes)
                    else raw_content
                )
        except DecryptionError:
            emit_admin_file_action(
                self.__class__,
                request,
                target_user,
                FileAuditLog.ACTION_PREVIEW,
                file_path,
                success=False,
                error_code="DECRYPTION_FAILED",
                error_message="Unable to decrypt file",
            )
            return Response(
                {
                    "error": {
                        "code": "DECRYPTION_FAILED",
                        "message": "Unable to decrypt file",
                        "path": file_path,
                    }
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        emit_admin_file_action(
            self.__class__,
            request,
            target_user,
            FileAuditLog.ACTION_PREVIEW,
            file_path,
            success=True,
            file_size=file_info.size,
        )

        return HttpResponse(content, content_type="text/plain; charset=utf-8")

    @extend_schema(
        summary="Edit user's file content (Admin)",
        description="Update text content of a file in user's storage.",
        responses={200: OpenApiResponse(description="File updated")},
        tags=["Admin - Files"],
    )
    def put(self, request: Request, user_id: int, file_path: str) -> Response:
        """Edit file content."""
        target_user = self.get_target_user(user_id)
        backend = LocalStorageBackend()
        user_prefix = get_target_user_storage_path(target_user)

        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            emit_admin_file_action(
                self.__class__,
                request,
                target_user,
                FileAuditLog.ACTION_EDIT,
                file_path,
                success=False,
                error_code="INVALID_PATH",
            )
            return Response(
                {"error": {"code": "INVALID_PATH", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        full_path = f"{user_prefix}/{file_path}"

        # Check file exists
        try:
            backend.info(full_path)
        except FileNotFoundError:
            emit_admin_file_action(
                self.__class__,
                request,
                target_user,
                FileAuditLog.ACTION_EDIT,
                file_path,
                success=False,
                error_code="FILE_NOT_FOUND",
            )
            return Response(
                {
                    "error": {
                        "code": "FILE_NOT_FOUND",
                        "message": f"File '{file_path}' not found.",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get content from request body
        raw_body = request.body
        content: str = (
            raw_body.decode("utf-8") if isinstance(raw_body, bytes) else raw_body
        )

        # Write content
        from io import BytesIO

        content_bytes = content.encode("utf-8")
        file_obj = BytesIO(content_bytes)
        file_obj.name = Path(file_path).name
        file_info = backend.save(full_path, file_obj)

        # Update database record
        StoredFile.objects.filter(owner=target_user.account, path=file_path).update(
            size=file_info.size,
            content_type=file_info.content_type or "text/plain",
        )

        emit_admin_file_action(
            self.__class__,
            request,
            target_user,
            FileAuditLog.ACTION_EDIT,
            file_path,
            success=True,
            file_size=file_info.size,
        )

        return Response(
            {
                "path": file_path,
                "size": file_info.size,
                "modified_at": file_info.modified_at,
                "target_user": {"id": target_user.id, "username": target_user.username},
            }
        )


# =============================================================================
# Bulk Operations
# =============================================================================


class AdminBulkOperationView(AdminFileBaseView):
    """Bulk operations on user's files (admin)."""

    @extend_schema(
        summary="Bulk file operations for user (Admin)",
        description="Perform bulk delete/move/copy operations on user's files.",
        responses={200: OpenApiResponse(description="Operation results")},
        tags=["Admin - Files"],
    )
    def post(self, request: Request, user_id: int) -> Response:
        """Execute bulk operation."""
        target_user = self.get_target_user(user_id)
        backend = LocalStorageBackend()

        operation = request.data.get("operation")
        paths = request.data.get("paths", [])
        options = request.data.get("options", {})

        if operation not in ["delete", "move", "copy"]:
            return Response(
                {
                    "error": {
                        "code": "INVALID_OPERATION",
                        "message": "Invalid operation.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not paths or len(paths) > 250:
            return Response(
                {"error": {"code": "INVALID_PATHS", "message": "Provide 1-250 paths."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Map operation to audit log action
        action_map = {
            "delete": FileAuditLog.ACTION_BULK_DELETE,
            "move": FileAuditLog.ACTION_BULK_MOVE,
            "copy": FileAuditLog.ACTION_BULK_COPY,
        }
        action = action_map[operation]

        # Use BulkOperationService
        service = BulkOperationService(target_user.account, backend)

        try:
            stats = service.execute(operation=operation, paths=paths, options=options)
        except ValueError as e:
            emit_admin_file_action(
                self.__class__,
                request,
                target_user,
                action,
                options.get("destination", "/"),
                success=False,
                error_code="INVALID_REQUEST",
                error_message=str(e),
                paths_affected=paths,
            )
            return Response(
                {"error": {"code": "INVALID_REQUEST", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        emit_admin_file_action(
            self.__class__,
            request,
            target_user,
            action,
            options.get("destination", "/"),
            success=stats.failed == 0,
            paths_affected=paths,
        )

        return Response(
            {
                "operation": operation,
                "total": stats.total,
                "succeeded": stats.succeeded,
                "failed": stats.failed,
                "results": [
                    {
                        "path": r.path,
                        "success": r.success,
                        "error_code": r.error_code,
                        "error_message": r.error_message,
                        "data": r.data,
                    }
                    for r in stats.results
                ],
                "target_user": {"id": target_user.id, "username": target_user.username},
            }
        )


# =============================================================================
# Audit Log Query
# =============================================================================


class FileAuditLogPagination(PageNumberPagination):
    """Pagination for audit logs."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class AdminFileAuditLogListView(AdminFileBaseView):
    """Query file audit logs (admin)."""

    pagination_class = FileAuditLogPagination

    @extend_schema(
        summary="Query file audit logs (Admin)",
        description="Query the file audit log with filters.",
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Filter by target user ID",
            ),
            OpenApiParameter(
                name="performed_by",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Filter by admin who performed action",
            ),
            OpenApiParameter(
                name="action",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter by action type (upload, download, delete, etc.)",
            ),
            OpenApiParameter(
                name="admin_only",
                type=bool,
                location=OpenApiParameter.QUERY,
                description="Only show admin actions",
            ),
            OpenApiParameter(
                name="success",
                type=bool,
                location=OpenApiParameter.QUERY,
                description="Filter by success/failure",
            ),
            OpenApiParameter(
                name="path",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter by path (contains match)",
            ),
            OpenApiParameter(
                name="from",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter from date (ISO format)",
            ),
            OpenApiParameter(
                name="to",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter to date (ISO format)",
            ),
        ],
        responses={200: FileAuditLogSerializer(many=True)},
        tags=["Admin - Audit"],
    )
    def get(self, request: Request) -> Response:
        """Query audit logs."""
        queryset = FileAuditLog.objects.all()

        # Apply filters
        user_id = request.query_params.get("user_id")
        if user_id:
            queryset = queryset.filter(target_user_id=user_id)

        performed_by = request.query_params.get("performed_by")
        if performed_by:
            queryset = queryset.filter(performed_by_id=performed_by)

        action = request.query_params.get("action")
        if action:
            queryset = queryset.filter(action=action)

        admin_only = request.query_params.get("admin_only")
        if admin_only and admin_only.lower() == "true":
            queryset = queryset.filter(is_admin_action=True)

        success = request.query_params.get("success")
        if success is not None:
            queryset = queryset.filter(success=success.lower() == "true")

        path = request.query_params.get("path")
        if path:
            queryset = queryset.filter(path__icontains=path)

        from_date = request.query_params.get("from")
        if from_date:
            try:
                from_dt = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
                queryset = queryset.filter(created_at__gte=from_dt)
            except ValueError:
                pass

        to_date = request.query_params.get("to")
        if to_date:
            try:
                to_dt = datetime.fromisoformat(to_date.replace("Z", "+00:00"))
                queryset = queryset.filter(created_at__lte=to_dt)
            except ValueError:
                pass

        # Paginate
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)

        serializer = FileAuditLogSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


# =============================================================================
# Admin Override Access
# =============================================================================


class AdminOverrideAccessView(AdminFileBaseView):
    """Request temporary override access to user's files with justification.

    This endpoint creates an audit trail for admin access to user files,
    requiring a justification that is logged. Returns a temporary access
    token valid for 1 hour.
    """

    @extend_schema(
        summary="Request admin override access (Admin)",
        description=(
            "Request temporary access to a user's files with required justification. "
            "Creates an audit log entry and returns a temporary access token."
        ),
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                location=OpenApiParameter.PATH,
                description="Target user ID",
            ),
            OpenApiParameter(
                name="file_path",
                type=str,
                location=OpenApiParameter.PATH,
                description="File/directory path to access (use * for all files)",
            ),
        ],
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "justification": {
                        "type": "string",
                        "description": "Required justification for accessing user's files",
                    },
                },
                "required": ["justification"],
            }
        },
        responses={
            200: OpenApiResponse(
                description="Access granted with temporary token",
                response={
                    "type": "object",
                    "properties": {
                        "access_granted": {"type": "boolean"},
                        "access_token": {"type": "string"},
                        "expires_at": {"type": "string", "format": "date-time"},
                        "target_user": {"type": "object"},
                        "path_prefix": {"type": "string"},
                    },
                },
            ),
            400: OpenApiResponse(description="Missing justification"),
        },
        tags=["Admin - Files"],
    )
    def post(self, request: Request, user_id: int, file_path: str = "") -> Response:
        """Request override access with justification."""
        from datetime import timedelta
        from django.utils import timezone
        from .models import AdminAccessToken

        target_user = self.get_target_user(user_id)

        # Validate justification
        justification = request.data.get("justification", "").strip()
        if not justification:
            return Response(
                {
                    "error": {
                        "code": "JUSTIFICATION_REQUIRED",
                        "message": "A justification is required for admin override access.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(justification) < 10:
            return Response(
                {
                    "error": {
                        "code": "JUSTIFICATION_TOO_SHORT",
                        "message": "Justification must be at least 10 characters.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Normalize path (use empty string for root/all access)
        try:
            path_prefix = (
                normalize_path(file_path) if file_path and file_path != "*" else ""
            )
        except PathValidationError as e:
            return Response(
                {"error": {"code": "INVALID_PATH", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create access token valid for 1 hour
        expires_at = timezone.now() + timedelta(hours=1)
        access_token = AdminAccessToken.objects.create(
            admin=request.user.account,
            target_user=target_user.account,
            path_prefix=path_prefix,
            justification=justification,
            expires_at=expires_at,
        )

        # Log the admin override action
        emit_admin_file_action(
            self.__class__,
            request,
            target_user,
            FileAuditLog.ACTION_ADMIN_OVERRIDE,
            path_prefix or "*",
            success=True,
            justification=justification,
        )

        return Response(
            {
                "access_granted": True,
                "access_token": str(access_token.token),
                "expires_at": expires_at.isoformat(),
                "target_user": {
                    "id": target_user.id,
                    "username": target_user.username,
                },
                "path_prefix": path_prefix or "*",
            }
        )
