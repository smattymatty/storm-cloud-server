"""API views for storage app."""

from base64 import b64encode, b64decode
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FileUploadParser
from django.http import FileResponse
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from pathlib import Path

from core.views import StormCloudBaseAPIView
from core.storage.local import LocalStorageBackend
from core.utils import normalize_path, PathValidationError
from core.throttling import UploadRateThrottle, DownloadRateThrottle
from .models import StoredFile
from .serializers import (
    DirectoryListResponseSerializer,
    FileListItemSerializer,
    FileUploadSerializer,
    FileInfoResponseSerializer,
    StoredFileSerializer,
)


def get_user_storage_path(user) -> str:
    """Get storage path prefix for user."""
    return f"{user.id}"


class DirectoryListView(StormCloudBaseAPIView):
    """List directory contents with pagination."""

    @extend_schema(
        summary="List directory",
        description="List contents of a directory. Returns files and subdirectories.",
        parameters=[
            OpenApiParameter('limit', int, description='Items per page (default 50, max 200)'),
            OpenApiParameter('cursor', str, description='Pagination cursor'),
        ],
        responses={
            200: DirectoryListResponseSerializer,
            404: OpenApiResponse(description="Directory not found"),
        },
        tags=['Files']
    )
    def get(self, request, dir_path=""):
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
                status=status.HTTP_400_BAD_REQUEST
            )

        # Construct full storage path
        full_path = f"{user_prefix}/{dir_path}" if dir_path else user_prefix

        try:
            entries = list(backend.list(full_path))
        except FileNotFoundError:
            # Auto-create user's root directory if it doesn't exist
            if not dir_path:
                backend.create_directory(full_path)
                entries = []
            else:
                return Response(
                    {
                        "error": {
                            "code": "DIRECTORY_NOT_FOUND",
                            "message": f"Directory '{dir_path}' does not exist.",
                            "path": dir_path,
                            "recovery": "Check the path and try again."
                        }
                    },
                    status=status.HTTP_404_NOT_FOUND
                )
        except NotADirectoryError:
            return Response(
                {
                    "error": {
                        "code": "PATH_IS_FILE",
                        "message": f"Path '{dir_path}' is a file, not a directory.",
                        "path": dir_path,
                        "recovery": f"Use GET /api/v1/files/{dir_path}/ for file metadata."
                    }
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Sort: directories first, then files alphabetically
        entries = sorted(entries, key=lambda x: (not x.is_directory, x.name))

        # Convert FileInfo objects to serializer format
        entry_data = [
            {
                'name': entry.name,
                'path': entry.path.replace(f"{user_prefix}/", ""),  # Strip user prefix
                'size': entry.size,
                'is_directory': entry.is_directory,
                'content_type': entry.content_type,
                'modified_at': entry.modified_at,
            }
            for entry in entries
        ]

        # Pagination
        limit = min(int(request.query_params.get('limit', 50)), 200)
        cursor = request.query_params.get('cursor')

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
            'path': dir_path,
            'entries': page_entries,
            'count': len(page_entries),
            'total': len(entry_data),
            'next_cursor': next_cursor,
        }

        return Response(response_data)


class DirectoryCreateView(StormCloudBaseAPIView):
    """Create directory."""

    @extend_schema(
        summary="Create directory",
        description="Create a new directory. Parent directories are created as needed.",
        responses={
            201: FileInfoResponseSerializer,
        },
        tags=['Files']
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
                status=status.HTTP_400_BAD_REQUEST
            )

        full_path = f"{user_prefix}/{dir_path}"

        #Check if directory already exists
        if backend.exists(full_path):
            return Response(
                {
                    "error": {
                        "code": "ALREADY_EXISTS",
                        "message": f"Directory '{dir_path}' already exists.",
                        "path": dir_path,
                    }
                },
                status=status.HTTP_409_CONFLICT
            )

        file_info = backend.mkdir(full_path)

        # Create database record
        parent_path = str(Path(dir_path).parent) if dir_path != "." else ""
        StoredFile.objects.update_or_create(
            owner=request.user,
            path=dir_path,
            defaults={
                'name': file_info.name,
                'size': 0,
                'content_type': '',
                'is_directory': True,
                'parent_path': parent_path,
            }
        )

        response_data = {
            'path': dir_path,
            'name': file_info.name,
            'size': 0,
            'content_type': None,
            'is_directory': True,
            'created_at': file_info.modified_at,
            'modified_at': file_info.modified_at,
        }

        return Response(response_data, status=status.HTTP_201_CREATED)


class FileDetailView(StormCloudBaseAPIView):
    """Get file metadata."""

    @extend_schema(
        summary="Get file metadata",
        description="Returns metadata for a file. Returns 404 if path is a directory.",
        responses={
            200: FileInfoResponseSerializer,
            404: OpenApiResponse(description="File not found"),
        },
        tags=['Files']
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
                status=status.HTTP_400_BAD_REQUEST
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
                        "recovery": "Check the path and try again."
                    }
                },
                status=status.HTTP_404_NOT_FOUND
            )

        if file_info.is_directory:
            return Response(
                {
                    "error": {
                        "code": "PATH_IS_DIRECTORY",
                        "message": f"Path '{file_path}' is a directory, not a file.",
                        "path": file_path,
                        "recovery": f"Use GET /api/v1/dirs/{file_path}/ to list directory contents."
                    }
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Try to get from database
        try:
            db_file = StoredFile.objects.get(owner=request.user, path=file_path)
            created_at = db_file.created_at
        except StoredFile.DoesNotExist:
            created_at = file_info.modified_at

        response_data = {
            'path': file_path,
            'name': file_info.name,
            'size': file_info.size,
            'content_type': file_info.content_type,
            'is_directory': False,
            'created_at': created_at,
            'modified_at': file_info.modified_at,
        }

        return Response(response_data)


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
        tags=['Files']
    )
    def post(self, request, file_path):
        """Upload file."""
        if 'file' not in request.FILES:
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "No file provided in request.",
                        "recovery": "Include a file in the request body with key 'file'."
                    }
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        uploaded_file = request.FILES['file']
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
                status=status.HTTP_400_BAD_REQUEST
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
        stored_file, created = StoredFile.objects.update_or_create(
            owner=request.user,
            path=file_path,
            defaults={
                'name': file_info.name,
                'size': file_info.size,
                'content_type': file_info.content_type or '',
                'is_directory': False,
                'parent_path': db_parent_path,
            }
        )

        response_data = {
            'path': file_path,
            'name': file_info.name,
            'size': file_info.size,
            'content_type': file_info.content_type,
            'is_directory': False,
            'created_at': stored_file.created_at,
            'modified_at': file_info.modified_at,
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
        tags=['Files']
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
                status=status.HTTP_400_BAD_REQUEST
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
                status=status.HTTP_404_NOT_FOUND
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
                status=status.HTTP_400_BAD_REQUEST
            )

        response = FileResponse(file_handle)
        if file_info.content_type:
            response['Content-Type'] = file_info.content_type
        response['Content-Disposition'] = f'attachment; filename="{file_info.name}"'

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
        tags=['Files']
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
                status=status.HTTP_400_BAD_REQUEST
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
                status=status.HTTP_404_NOT_FOUND
            )

        # Delete from database
        StoredFile.objects.filter(owner=request.user, path=file_path).delete()

        return Response({
            "message": "File deleted successfully",
            "path": file_path
        })


class IndexRebuildView(StormCloudBaseAPIView):
    """Rebuild file index from filesystem (admin only)."""

    @extend_schema(
        summary="Rebuild file index",
        description="Reconcile database with filesystem. Admin only. NOT IMPLEMENTED in Phase 1.",
        responses={
            501: OpenApiResponse(description="Not implemented"),
        },
        tags=['Administration']
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
            status=status.HTTP_501_NOT_IMPLEMENTED
        )
