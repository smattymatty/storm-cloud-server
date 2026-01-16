"""API views for shared organization storage."""

from io import BytesIO
from pathlib import Path
from typing import Any, cast

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import F, Sum
from django.http import FileResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema

from rest_framework import status
from rest_framework.parsers import FileUploadParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from core.services.encryption import DecryptionError
from core.storage.local import LocalStorageBackend
from core.throttling import DownloadRateThrottle, UploadRateThrottle
from core.utils import PathValidationError, normalize_path
from core.views import StormCloudBaseAPIView

from accounts.permissions import check_max_upload_size, check_user_permission

from .models import FileAuditLog, StoredFile
from .signals import file_action_performed
from .serializers import (
    DirectoryListResponseSerializer,
    FileInfoResponseSerializer,
    FileListItemSerializer,
    FileUploadSerializer,
)
from .services import generate_etag, is_text_file


def emit_shared_file_action(
    sender: Any,
    request: Request,
    action: str,
    path: str,
    success: bool = True,
    **kwargs: Any,
) -> None:
    """Emit file action signal for shared file operations.

    Creates audit log entry for organization shared file operations.
    """
    file_action_performed.send(
        sender=sender,
        performed_by=request.user,
        target_user=request.user,  # User performing the action
        is_admin_action=False,
        action=action,
        path=f"[shared] {path}",  # Prefix to distinguish in audit logs
        success=success,
        request=request,
        **kwargs,
    )


class SharedStorageBaseMixin:
    """Mixin providing shared storage access utilities."""

    def get_org_and_backend(self, request: Request):
        """Get user's organization and storage backend.

        Returns:
            tuple: (organization, backend) or raises appropriate error

        Raises:
            Response: 403 if user has no organization
        """
        account = request.user.account
        org = account.organization

        if not org:
            return None, None

        backend = LocalStorageBackend()
        return org, backend

    def check_org_access(self, request: Request) -> Response | None:
        """Check if user has access to shared storage.

        Returns:
            Response with error if no access, None if access granted
        """
        org, _ = self.get_org_and_backend(request)
        if not org:
            return Response(
                {
                    "error": {
                        "code": "NO_ORGANIZATION",
                        "message": "You must belong to an organization to access shared storage.",
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        return None


class SharedDirectoryListRootView(SharedStorageBaseMixin, StormCloudBaseAPIView):
    """List root of shared organization storage."""

    @extend_schema(
        operation_id="v1_shared_dirs_list_root",
        summary="List shared root directory",
        description="List contents of the organization's shared storage root.",
        parameters=[
            OpenApiParameter(
                "limit", int, description="Items per page (default 50, max 200)"
            ),
            OpenApiParameter("cursor", str, description="Pagination cursor"),
            OpenApiParameter(
                "search", str, description="Filter by name (case-insensitive contains)"
            ),
        ],
        responses={200: DirectoryListResponseSerializer},
        tags=["Shared Storage"],
    )
    def get(self, request: Request) -> Response:
        """List shared root directory."""
        error = self.check_org_access(request)
        if error:
            return error

        return self._list_directory(request, dir_path="")

    def _list_directory(self, request: Request, dir_path: str = "") -> Response:
        """List shared directory contents with pagination."""
        org, backend = self.get_org_and_backend(request)

        limit = min(int(request.query_params.get("limit", 50)), 200)
        cursor = request.query_params.get("cursor")
        search = request.query_params.get("search", "").strip() or None

        # Query database for shared files
        queryset = StoredFile.objects.filter(
            organization=org,
            parent_path=dir_path,
        )

        if search:
            queryset = queryset.filter(name__icontains=search)

        # Pagination using cursor (created_at based)
        if cursor:
            try:
                from django.utils.dateparse import parse_datetime
                cursor_dt = parse_datetime(cursor)
                if cursor_dt:
                    queryset = queryset.filter(created_at__lt=cursor_dt)
            except (ValueError, TypeError):
                pass

        # Sort: custom position first, then by name
        queryset = queryset.order_by(
            F("sort_position").asc(nulls_last=True), "name"
        )[:limit + 1]

        items = list(queryset)
        has_more = len(items) > limit
        items = items[:limit]

        next_cursor = None
        if has_more and items:
            next_cursor = items[-1].created_at.isoformat()

        # Log directory list action
        emit_shared_file_action(
            sender=self.__class__,
            request=request,
            action=FileAuditLog.ACTION_LIST,
            path=dir_path or "/",
        )

        serializer = FileListItemSerializer(items, many=True)
        return Response(
            {
                "path": dir_path,
                "items": serializer.data,
                "next_cursor": next_cursor,
            }
        )


class SharedDirectoryListView(SharedStorageBaseMixin, StormCloudBaseAPIView):
    """List contents of a shared directory."""

    @extend_schema(
        operation_id="v1_shared_dirs_list",
        summary="List shared directory",
        description="List contents of a shared directory.",
        parameters=[
            OpenApiParameter(
                "limit", int, description="Items per page (default 50, max 200)"
            ),
            OpenApiParameter("cursor", str, description="Pagination cursor"),
            OpenApiParameter(
                "search", str, description="Filter by name (case-insensitive contains)"
            ),
        ],
        responses={200: DirectoryListResponseSerializer},
        tags=["Shared Storage"],
    )
    def get(self, request: Request, dir_path: str) -> Response:
        """List shared directory contents."""
        error = self.check_org_access(request)
        if error:
            return error

        org, backend = self.get_org_and_backend(request)

        # Normalize path
        try:
            dir_path = normalize_path(dir_path)
        except PathValidationError as e:
            return Response(
                {"error": {"code": "INVALID_PATH", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check directory exists
        if not backend.exists_shared(org.id, dir_path):
            return Response(
                {"error": {"code": "NOT_FOUND", "message": f"Directory not found: {dir_path}"}},
                status=status.HTTP_404_NOT_FOUND,
            )

        return SharedDirectoryListRootView()._list_directory(request, dir_path)


class SharedDirectoryCreateView(SharedStorageBaseMixin, StormCloudBaseAPIView):
    """Create a directory in shared storage."""

    @extend_schema(
        operation_id="v1_shared_dirs_create",
        summary="Create shared directory",
        description="Create a directory in the organization's shared storage.",
        responses={201: FileInfoResponseSerializer},
        tags=["Shared Storage"],
    )
    def post(self, request: Request, dir_path: str) -> Response:
        """Create shared directory."""
        error = self.check_org_access(request)
        if error:
            return error

        org, backend = self.get_org_and_backend(request)

        # Normalize path
        try:
            dir_path = normalize_path(dir_path)
        except PathValidationError as e:
            return Response(
                {"error": {"code": "INVALID_PATH", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if already exists
        if backend.exists_shared(org.id, dir_path):
            return Response(
                {"error": {"code": "ALREADY_EXISTS", "message": f"Path already exists: {dir_path}"}},
                status=status.HTTP_409_CONFLICT,
            )

        # Create directory on filesystem
        file_info = backend.mkdir_shared(org.id, dir_path)

        # Create database record
        parent_path = str(Path(dir_path).parent) if "/" in dir_path else ""
        if parent_path == ".":
            parent_path = ""

        stored_file = StoredFile.objects.create(
            organization=org,
            path=dir_path,
            name=file_info.name,
            size=0,
            is_directory=True,
            parent_path=parent_path,
            encryption_method=StoredFile.ENCRYPTION_NONE,
        )

        emit_shared_file_action(
            sender=self.__class__,
            request=request,
            action=FileAuditLog.ACTION_CREATE_DIR,
            path=dir_path,
        )

        return Response(
            {
                "path": dir_path,
                "name": file_info.name,
                "size": 0,
                "is_directory": True,
                "created_at": stored_file.created_at,
                "modified_at": file_info.modified_at,
            },
            status=status.HTTP_201_CREATED,
        )


class SharedFileDetailView(SharedStorageBaseMixin, StormCloudBaseAPIView):
    """Get shared file metadata."""

    @extend_schema(
        operation_id="v1_shared_files_detail",
        summary="Get shared file info",
        description="Get metadata for a shared file.",
        responses={200: FileInfoResponseSerializer},
        tags=["Shared Storage"],
    )
    def get(self, request: Request, file_path: str) -> Response:
        """Get shared file metadata."""
        error = self.check_org_access(request)
        if error:
            return error

        org, backend = self.get_org_and_backend(request)

        # Normalize path
        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            return Response(
                {"error": {"code": "INVALID_PATH", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get from database
        try:
            stored_file = StoredFile.objects.get(organization=org, path=file_path)
        except StoredFile.DoesNotExist:
            return Response(
                {"error": {"code": "NOT_FOUND", "message": f"File not found: {file_path}"}},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Generate ETag
        etag = generate_etag(file_path, stored_file.size, stored_file.updated_at)

        response_data = {
            "path": stored_file.path,
            "name": stored_file.name,
            "size": stored_file.size,
            "content_type": stored_file.content_type,
            "is_directory": stored_file.is_directory,
            "created_at": stored_file.created_at,
            "modified_at": stored_file.updated_at,
            "encryption_method": stored_file.encryption_method,
        }

        response = Response(response_data)
        response["ETag"] = f'"{etag}"'
        return response


class SharedFileUploadView(SharedStorageBaseMixin, StormCloudBaseAPIView):
    """Upload file to shared storage."""

    parser_classes = [MultiPartParser, FileUploadParser]
    throttle_classes = [UploadRateThrottle]

    @extend_schema(
        operation_id="v1_shared_files_upload",
        summary="Upload shared file",
        description="Upload a file to the organization's shared storage.",
        request=FileUploadSerializer,
        responses={201: FileInfoResponseSerializer},
        tags=["Shared Storage"],
    )
    def post(self, request: Request, file_path: str) -> Response:
        """Upload file to shared storage."""
        error = self.check_org_access(request)
        if error:
            return error

        if "file" not in request.FILES:
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "No file provided in request.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        uploaded_file = request.FILES["file"]
        org, backend = self.get_org_and_backend(request)

        # Check user permission to upload
        check_user_permission(request.user, "can_upload")

        # Check per-user file size limit
        check_max_upload_size(request.user, uploaded_file.size)

        # Check global size limit
        max_size = settings.STORMCLOUD_MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if uploaded_file.size > max_size:
            emit_shared_file_action(
                sender=self.__class__,
                request=request,
                action=FileAuditLog.ACTION_UPLOAD,
                path=file_path,
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

        # Normalize path
        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            return Response(
                {"error": {"code": "INVALID_PATH", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check org quota
        org_quota = org.storage_quota_bytes
        if org_quota > 0:
            current_usage = (
                StoredFile.objects.filter(organization=org).aggregate(
                    total=Sum("size")
                )["total"]
                or 0
            )

            # Check for overwrite
            is_overwrite = StoredFile.objects.filter(
                organization=org, path=file_path
            ).exists()

            size_delta = uploaded_file.size
            if is_overwrite:
                old_file = StoredFile.objects.get(organization=org, path=file_path)
                size_delta = uploaded_file.size - old_file.size

            if current_usage + size_delta > org_quota:
                emit_shared_file_action(
                    sender=self.__class__,
                    request=request,
                    action=FileAuditLog.ACTION_UPLOAD,
                    path=file_path,
                    success=False,
                    error_code="QUOTA_EXCEEDED",
                )
                return Response(
                    {
                        "error": {
                            "code": "QUOTA_EXCEEDED",
                            "message": "Upload would exceed organization storage quota",
                            "quota_mb": round(org_quota / (1024 * 1024), 2),
                            "used_mb": round(current_usage / (1024 * 1024), 2),
                        }
                    },
                    status=status.HTTP_507_INSUFFICIENT_STORAGE,
                )

        # Ensure parent directory exists
        parent_path = str(Path(file_path).parent) if "/" in file_path else ""
        if parent_path and parent_path != ".":
            if not backend.exists_shared(org.id, parent_path):
                backend.mkdir_shared(org.id, parent_path)
        else:
            # Ensure org root exists
            backend.get_org_storage_root(org.id)

        # Save file
        file_info = backend.save_shared(org.id, file_path, uploaded_file)

        # Create/update database record
        db_parent_path = str(Path(file_path).parent) if "/" in file_path else ""
        if db_parent_path == ".":
            db_parent_path = ""

        stored_file, created = StoredFile.objects.update_or_create(
            organization=org,
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

        emit_shared_file_action(
            sender=self.__class__,
            request=request,
            action=FileAuditLog.ACTION_UPLOAD,
            path=file_path,
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
                "encryption_method": stored_file.encryption_method,
            },
            status=status.HTTP_201_CREATED,
        )


class SharedFileDownloadView(SharedStorageBaseMixin, StormCloudBaseAPIView):
    """Download file from shared storage."""

    throttle_classes = [DownloadRateThrottle]

    @extend_schema(
        operation_id="v1_shared_files_download",
        summary="Download shared file",
        description="Download a file from the organization's shared storage.",
        tags=["Shared Storage"],
    )
    def get(self, request: Request, file_path: str) -> Response:
        """Download shared file."""
        error = self.check_org_access(request)
        if error:
            return error

        org, backend = self.get_org_and_backend(request)

        # Normalize path
        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            return Response(
                {"error": {"code": "INVALID_PATH", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get from database
        try:
            stored_file = StoredFile.objects.get(organization=org, path=file_path)
        except StoredFile.DoesNotExist:
            return Response(
                {"error": {"code": "NOT_FOUND", "message": f"File not found: {file_path}"}},
                status=status.HTTP_404_NOT_FOUND,
            )

        if stored_file.is_directory:
            return Response(
                {"error": {"code": "IS_DIRECTORY", "message": "Cannot download a directory"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Generate ETag and check conditional request
        etag = generate_etag(file_path, stored_file.size, stored_file.updated_at)
        if_none_match = request.META.get("HTTP_IF_NONE_MATCH", "").strip('"')

        if if_none_match == etag:
            emit_shared_file_action(
                sender=self.__class__,
                request=request,
                action=FileAuditLog.ACTION_DOWNLOAD,
                path=file_path,
            )
            response = Response(status=status.HTTP_304_NOT_MODIFIED)
            response["ETag"] = f'"{etag}"'
            return response

        # Open and stream file
        try:
            file_handle = backend.open_shared(org.id, file_path)
        except FileNotFoundError:
            return Response(
                {"error": {"code": "NOT_FOUND", "message": f"File not found: {file_path}"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        except DecryptionError:
            return Response(
                {"error": {"code": "DECRYPTION_FAILED", "message": "Failed to decrypt file"}},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        emit_shared_file_action(
            sender=self.__class__,
            request=request,
            action=FileAuditLog.ACTION_DOWNLOAD,
            path=file_path,
            file_size=stored_file.size,
            content_type=stored_file.content_type,
        )

        response = FileResponse(
            file_handle,
            content_type=stored_file.content_type or "application/octet-stream",
            as_attachment=True,
            filename=stored_file.name,
        )
        response["ETag"] = f'"{etag}"'
        return response


class SharedFileDeleteView(SharedStorageBaseMixin, StormCloudBaseAPIView):
    """Delete file from shared storage."""

    @extend_schema(
        operation_id="v1_shared_files_delete",
        summary="Delete shared file",
        description="Delete a file or directory from the organization's shared storage.",
        tags=["Shared Storage"],
    )
    def delete(self, request: Request, file_path: str) -> Response:
        """Delete shared file or directory."""
        error = self.check_org_access(request)
        if error:
            return error

        # Check permission
        check_user_permission(request.user, "can_delete")

        org, backend = self.get_org_and_backend(request)

        # Normalize path
        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            return Response(
                {"error": {"code": "INVALID_PATH", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get from database
        try:
            stored_file = StoredFile.objects.get(organization=org, path=file_path)
        except StoredFile.DoesNotExist:
            return Response(
                {"error": {"code": "NOT_FOUND", "message": f"File not found: {file_path}"}},
                status=status.HTTP_404_NOT_FOUND,
            )

        # If directory, recursively delete contents
        if stored_file.is_directory:
            # Delete all children from DB
            StoredFile.objects.filter(
                organization=org, path__startswith=f"{file_path}/"
            ).delete()

            # Delete from filesystem recursively
            import shutil
            full_path = backend._resolve_shared_path(org.id, file_path)
            if full_path.exists():
                shutil.rmtree(full_path)
        else:
            # Delete single file
            try:
                backend.delete_shared(org.id, file_path)
            except FileNotFoundError:
                pass  # Already deleted from filesystem

        # Delete DB record
        stored_file.delete()

        emit_shared_file_action(
            sender=self.__class__,
            request=request,
            action=FileAuditLog.ACTION_DELETE,
            path=file_path,
        )

        return Response({"message": f"Deleted: {file_path}"}, status=status.HTTP_200_OK)


class SharedFileContentView(SharedStorageBaseMixin, StormCloudBaseAPIView):
    """Preview and edit shared text file content."""

    @extend_schema(
        operation_id="v1_shared_files_content_get",
        summary="Preview shared file content",
        description="Get the content of a shared text file for preview.",
        tags=["Shared Storage"],
    )
    def get(self, request: Request, file_path: str) -> Response:
        """Get shared text file content."""
        error = self.check_org_access(request)
        if error:
            return error

        org, backend = self.get_org_and_backend(request)

        # Normalize path
        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            return Response(
                {"error": {"code": "INVALID_PATH", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get from database
        try:
            stored_file = StoredFile.objects.get(organization=org, path=file_path)
        except StoredFile.DoesNotExist:
            return Response(
                {"error": {"code": "NOT_FOUND", "message": f"File not found: {file_path}"}},
                status=status.HTTP_404_NOT_FOUND,
            )

        if stored_file.is_directory:
            return Response(
                {"error": {"code": "IS_DIRECTORY", "message": "Cannot preview directory"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if text file
        if not is_text_file(stored_file.name, stored_file.content_type):
            return Response(
                {"error": {"code": "NOT_TEXT_FILE", "message": "File is not a text file"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check size limit
        max_preview_size = settings.STORMCLOUD_MAX_PREVIEW_SIZE_MB * 1024 * 1024
        if stored_file.size > max_preview_size:
            return Response(
                {
                    "error": {
                        "code": "FILE_TOO_LARGE",
                        "message": f"File too large for preview (max {settings.STORMCLOUD_MAX_PREVIEW_SIZE_MB}MB)",
                    }
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        # Read content
        try:
            file_handle = backend.open_shared(org.id, file_path)
            content = file_handle.read().decode("utf-8")
        except (FileNotFoundError, DecryptionError) as e:
            return Response(
                {"error": {"code": "READ_ERROR", "message": str(e)}},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except UnicodeDecodeError:
            return Response(
                {"error": {"code": "NOT_TEXT_FILE", "message": "File is not valid UTF-8 text"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        emit_shared_file_action(
            sender=self.__class__,
            request=request,
            action=FileAuditLog.ACTION_PREVIEW,
            path=file_path,
        )

        from django.http import HttpResponse
        return HttpResponse(content, content_type="text/plain; charset=utf-8")

    @extend_schema(
        operation_id="v1_shared_files_content_put",
        summary="Edit shared file content",
        description="Update the content of a shared text file.",
        tags=["Shared Storage"],
    )
    def put(self, request: Request, file_path: str) -> Response:
        """Update shared text file content."""
        error = self.check_org_access(request)
        if error:
            return error

        check_user_permission(request.user, "can_overwrite")

        org, backend = self.get_org_and_backend(request)

        # Normalize path
        try:
            file_path = normalize_path(file_path)
        except PathValidationError as e:
            return Response(
                {"error": {"code": "INVALID_PATH", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get from database
        try:
            stored_file = StoredFile.objects.get(organization=org, path=file_path)
        except StoredFile.DoesNotExist:
            return Response(
                {"error": {"code": "NOT_FOUND", "message": f"File not found: {file_path}"}},
                status=status.HTTP_404_NOT_FOUND,
            )

        if stored_file.is_directory:
            return Response(
                {"error": {"code": "IS_DIRECTORY", "message": "Cannot edit directory"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get content from request body
        content = request.body
        if isinstance(content, bytes):
            try:
                content = content.decode("utf-8")
            except UnicodeDecodeError:
                return Response(
                    {"error": {"code": "INVALID_CONTENT", "message": "Content must be valid UTF-8"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Check size limit
        max_size = settings.STORMCLOUD_MAX_UPLOAD_SIZE_MB * 1024 * 1024
        content_bytes = content.encode("utf-8")
        if len(content_bytes) > max_size:
            return Response(
                {"error": {"code": "FILE_TOO_LARGE", "message": "Content too large"}},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        # Check org quota
        org_quota = org.storage_quota_bytes
        if org_quota > 0:
            current_usage = (
                StoredFile.objects.filter(organization=org).aggregate(
                    total=Sum("size")
                )["total"]
                or 0
            )
            size_delta = len(content_bytes) - stored_file.size
            if current_usage + size_delta > org_quota:
                return Response(
                    {"error": {"code": "QUOTA_EXCEEDED", "message": "Edit would exceed organization quota"}},
                    status=status.HTTP_507_INSUFFICIENT_STORAGE,
                )

        # Save content
        file_info = backend.save_shared(org.id, file_path, BytesIO(content_bytes))

        # Update database
        stored_file.size = file_info.size
        stored_file.encryption_method = file_info.encryption_method
        stored_file.key_id = file_info.encryption_key_id
        stored_file.encrypted_size = file_info.encrypted_size
        stored_file.save()

        emit_shared_file_action(
            sender=self.__class__,
            request=request,
            action=FileAuditLog.ACTION_EDIT,
            path=file_path,
            file_size=file_info.size,
        )

        return Response(
            {
                "path": file_path,
                "name": stored_file.name,
                "size": file_info.size,
                "modified_at": stored_file.updated_at,
            }
        )
