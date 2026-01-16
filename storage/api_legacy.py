"""API views for storage app."""

import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Optional, Union, cast

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import F, Q, Sum
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from datetime import datetime

from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FileUploadParser, MultiPartParser
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response

from core.services.encryption import DecryptionError
from core.storage.local import LocalStorageBackend
from core.throttling import (
    DownloadRateThrottle,
    UploadRateThrottle,
)
from core.utils import PathValidationError, normalize_path
from core.views import StormCloudBaseAPIView

from accounts.permissions import (
    check_max_upload_size,
    check_user_permission,
)

from .models import FileAuditLog, StoredFile
from .signals import file_action_performed
from .serializers import (
    FileAuditLogSerializer,
    FileInfoResponseSerializer,
    FileListItemSerializer,
    FileUploadSerializer,
    StoredFileSerializer,
)
from .services import (
    FileService,
    generate_etag,
    get_user_storage_path,
    is_text_file,
)

from accounts.services.webhook import trigger_webhook


def emit_user_file_action(
    sender: Any,
    request: Request,
    action: str,
    path: str,
    success: bool = True,
    **kwargs: Any,
) -> None:
    """Emit file action signal for user operations.

    Creates audit log entry for regular user file operations.
    For admin operations, use emit_admin_file_action() in admin_api.py.
    """
    file_action_performed.send(
        sender=sender,
        performed_by=request.user,
        target_user=request.user,  # User is acting on their own files
        is_admin_action=False,
        action=action,
        path=path,
        success=success,
        request=request,
        **kwargs,
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
        service = FileService(request.user.account)
        result = service.get_info(file_path)

        if not result.success:
            error_status = status.HTTP_400_BAD_REQUEST
            if result.error_code == "FILE_NOT_FOUND":
                error_status = status.HTTP_404_NOT_FOUND

            return Response(
                {
                    "error": {
                        "code": result.error_code,
                        "message": result.error_message,
                        "path": file_path,
                    }
                },
                status=error_status,
            )

        # Check conditional request (If-None-Match header)
        if_none_match = request.headers.get("If-None-Match", "").strip('"')
        if if_none_match == result.etag:
            response = Response(status=status.HTTP_304_NOT_MODIFIED)
            response["ETag"] = f'"{result.etag}"'
            return response

        response_data = {
            "path": result.path,
            "name": result.name,
            "size": result.size,
            "content_type": result.content_type,
            "is_directory": result.is_directory,
            "created_at": result.created_at,
            "modified_at": result.modified_at,
            "encryption_method": result.encryption_method,
        }

        response = Response(response_data)
        response["ETag"] = f'"{result.etag}"'
        response["Cache-Control"] = "private, must-revalidate"
        return response


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
            emit_user_file_action(
                sender=self.__class__,
                request=request,
                action=FileAuditLog.ACTION_UPLOAD,
                path=file_path,
                success=False,
                error_code="ALREADY_EXISTS",
                error_message=f"File '{file_path}' already exists.",
            )
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
            owner=request.user.account,
            parent_path=db_parent_path,
            sort_position__isnull=False,
        ).update(sort_position=F("sort_position") + 1)

        stored_file, created = StoredFile.objects.update_or_create(
            owner=request.user.account,
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

        # Log successful file creation
        emit_user_file_action(
            sender=self.__class__,
            request=request,
            action=FileAuditLog.ACTION_UPLOAD,
            path=file_path,
            file_size=0,
            content_type=content_type,
        )

        # Trigger webhook notification
        trigger_webhook(request.auth, "file.created", file_path)

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

        # Check user permission to upload
        check_user_permission(request.user, "can_upload")

        # Check per-user file size limit
        check_max_upload_size(request.user, uploaded_file.size)

        # P0-3: Validate file size against global limit
        max_size = settings.STORMCLOUD_MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if uploaded_file.size > max_size:
            emit_user_file_action(
                sender=self.__class__,
                request=request,
                action=FileAuditLog.ACTION_UPLOAD,
                path=file_path,
                success=False,
                error_code="FILE_TOO_LARGE",
                error_message="File size exceeds maximum allowed size",
                file_size=uploaded_file.size,
            )
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

        # Check if this is an overwrite (file already exists)
        is_overwrite = StoredFile.objects.filter(
            owner=request.user.account, path=file_path
        ).exists()
        if is_overwrite:
            check_user_permission(request.user, "can_overwrite")

        # P0-3: Validate against user quota (if set)
        # IsAuthenticated permission guarantees user is not AnonymousUser
        assert not request.user.is_anonymous
        profile = getattr(request.user, 'account', None)
        # API key auth doesn't have per-user quota, use 0 (unlimited/server default)
        quota_bytes = profile.storage_quota_bytes if profile else 0
        if quota_bytes > 0:  # 0 = unlimited
            # Calculate user's current storage usage
            current_usage = (
                StoredFile.objects.filter(owner=request.user.account).aggregate(
                    total=Sum("size")
                )["total"]
                or 0
            )

            # For file replacement (overwrite), calculate delta instead of full size
            size_delta = uploaded_file.size
            if is_overwrite:
                old_file = StoredFile.objects.get(owner=request.user.account, path=file_path)
                size_delta = uploaded_file.size - old_file.size

            if current_usage + size_delta > quota_bytes:
                space_needed = (current_usage + size_delta - quota_bytes) / (
                    1024 * 1024
                )
                emit_user_file_action(
                    sender=self.__class__,
                    request=request,
                    action=FileAuditLog.ACTION_UPLOAD,
                    path=file_path,
                    success=False,
                    error_code="QUOTA_EXCEEDED",
                    error_message="Upload would exceed your storage quota",
                    file_size=uploaded_file.size,
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
            owner=request.user.account,
            parent_path=db_parent_path,
            sort_position__isnull=False,
        ).update(sort_position=F("sort_position") + 1)

        stored_file, created = StoredFile.objects.update_or_create(
            owner=request.user.account,
            path=file_path,
            defaults={
                "name": file_info.name,
                "size": file_info.size,
                "content_type": file_info.content_type or "",
                "is_directory": False,
                "parent_path": db_parent_path,
                # Encryption metadata from backend (ADR 010)
                "encryption_method": file_info.encryption_method,
                "key_id": file_info.encryption_key_id,
                "encrypted_size": file_info.encrypted_size,
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

        # Log successful file upload
        emit_user_file_action(
            sender=self.__class__,
            request=request,
            action=FileAuditLog.ACTION_UPLOAD,
            path=file_path,
            file_size=file_info.size,
            content_type=file_info.content_type,
        )

        # Trigger webhook notification
        event = "file.created" if created else "file.updated"
        trigger_webhook(request.auth, event, file_path)

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

        # Get file metadata first (no file I/O)
        try:
            file_info = backend.info(full_path)
        except FileNotFoundError:
            emit_user_file_action(
                sender=self.__class__,
                request=request,
                action=FileAuditLog.ACTION_DOWNLOAD,
                path=file_path,
                success=False,
                error_code="FILE_NOT_FOUND",
                error_message=f"File '{file_path}' does not exist.",
            )
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

        # Generate ETag and check conditional request before opening file
        etag = generate_etag(file_path, file_info.size, file_info.modified_at)
        if_none_match = request.headers.get("If-None-Match", "").strip('"')
        if if_none_match == etag:
            response = HttpResponse(status=304)
            response["ETag"] = f'"{etag}"'
            return response

        # Only open file if we actually need to send content
        try:
            file_handle = backend.open(full_path)
        except DecryptionError:
            emit_user_file_action(
                sender=self.__class__,
                request=request,
                action=FileAuditLog.ACTION_DOWNLOAD,
                path=file_path,
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

        # Log successful download
        emit_user_file_action(
            sender=self.__class__,
            request=request,
            action=FileAuditLog.ACTION_DOWNLOAD,
            path=file_path,
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
            emit_user_file_action(
                sender=self.__class__,
                request=request,
                action=FileAuditLog.ACTION_PREVIEW,
                path=file_path,
                success=False,
                error_code="FILE_NOT_FOUND",
                error_message=f"File '{file_path}' does not exist.",
            )
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
        except DecryptionError:
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
        except Exception as e:
            return Response(
                {"error": {"code": "READ_ERROR", "message": str(e)}},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Log successful preview
        emit_user_file_action(
            sender=self.__class__,
            request=request,
            action=FileAuditLog.ACTION_PREVIEW,
            path=file_path,
            file_size=file_info.size,
            content_type=file_info.content_type,
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
        # Check user permission to overwrite files
        check_user_permission(request.user, "can_overwrite")

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
            emit_user_file_action(
                sender=self.__class__,
                request=request,
                action=FileAuditLog.ACTION_EDIT,
                path=file_path,
                success=False,
                error_code="FILE_NOT_FOUND",
                error_message=f"File '{file_path}' does not exist.",
            )
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
            emit_user_file_action(
                sender=self.__class__,
                request=request,
                action=FileAuditLog.ACTION_EDIT,
                path=file_path,
                success=False,
                error_code="FILE_TOO_LARGE",
                error_message="Content exceeds maximum allowed size.",
                file_size=new_size,
            )
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
        profile = request.user.account  # type: ignore[union-attr]
        quota_bytes = profile.storage_quota_bytes
        if quota_bytes > 0:
            current_usage = (
                StoredFile.objects.filter(owner=request.user.account).aggregate(
                    total=Sum("size")
                )["total"]
                or 0
            )
            old_size = old_info.size
            size_delta = new_size - old_size

            if current_usage + size_delta > quota_bytes:
                emit_user_file_action(
                    sender=self.__class__,
                    request=request,
                    action=FileAuditLog.ACTION_EDIT,
                    path=file_path,
                    success=False,
                    error_code="QUOTA_EXCEEDED",
                    error_message="Edit would exceed your storage quota.",
                    file_size=new_size,
                )
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
            owner=request.user.account,
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

        # Log successful edit
        emit_user_file_action(
            sender=self.__class__,
            request=request,
            action=FileAuditLog.ACTION_EDIT,
            path=file_path,
            file_size=file_info.size,
            content_type=file_info.content_type,
        )

        # Trigger webhook notification
        trigger_webhook(request.auth, "file.updated", file_path)

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
        # Check user permission to delete
        check_user_permission(request.user, "can_delete")

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
            emit_user_file_action(
                sender=self.__class__,
                request=request,
                action=FileAuditLog.ACTION_DELETE,
                path=file_path,
                success=False,
                error_code="FILE_NOT_FOUND",
                error_message=f"File '{file_path}' does not exist.",
            )
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
        StoredFile.objects.filter(owner=request.user.account, path=file_path).delete()

        # Log successful delete
        emit_user_file_action(
            sender=self.__class__,
            request=request,
            action=FileAuditLog.ACTION_DELETE,
            path=file_path,
        )

        # Trigger webhook notification
        trigger_webhook(request.auth, "file.deleted", file_path)

        return Response({"message": "File deleted successfully", "path": file_path})


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

        # Check permission based on operation type
        permission_map = {
            "delete": "can_delete",
            "move": "can_move",
            "copy": "can_upload",  # Copy creates new files
        }
        required_permission = permission_map.get(operation)
        if required_permission:
            check_user_permission(request.user, required_permission)

        # Create service and execute
        backend = LocalStorageBackend()
        service = BulkOperationService(account=request.user.account, backend=backend)

        try:
            result = service.execute(operation=operation, paths=paths, options=options)
        except ValueError as e:
            return Response(
                {"error": {"code": "INVALID_REQUEST", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Map operation to audit log action
        action_map = {
            "delete": FileAuditLog.ACTION_BULK_DELETE,
            "move": FileAuditLog.ACTION_BULK_MOVE,
            "copy": FileAuditLog.ACTION_BULK_COPY,
        }
        audit_action = action_map.get(operation, operation)

        # Check if async
        if isinstance(result, dict) and result.get("async"):
            # For async operations, log that the operation was queued
            emit_user_file_action(
                sender=self.__class__,
                request=request,
                action=audit_action,
                path=options.get("destination", ""),
                paths_affected=paths,
                destination_path=options.get("destination"),
            )
            async_serializer = BulkOperationAsyncResponseSerializer(result)
            return Response(async_serializer.data, status=status.HTTP_202_ACCEPTED)
        else:
            # Sync result - log with success/failure counts
            emit_user_file_action(
                sender=self.__class__,
                request=request,
                action=audit_action,
                path=options.get("destination", ""),
                paths_affected=paths,
                destination_path=options.get("destination"),
            )
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

        # Verify ownership - task args contain account_id
        task_args = getattr(task_result, "args", None) or {}
        task_account_id = task_args.get("account_id")
        if task_account_id != str(request.user.account.id):  # type: ignore[union-attr]
            return Response(
                {
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "Not authorized to view this task",
                        "task_id": task_id,
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

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
