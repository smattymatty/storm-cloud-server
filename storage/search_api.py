"""Recursive file search API views."""

import os
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import Any, Optional

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response

from core.storage.local import LocalStorageBackend
from core.utils import PathValidationError, normalize_path
from core.views import StormCloudBaseAPIView

from .services import get_user_storage_path


User = get_user_model()

# Constants
DEFAULT_LIMIT = 100
MAX_LIMIT = 500


class SearchFilesView(StormCloudBaseAPIView):
    """Recursive file search for authenticated users."""

    @extend_schema(
        operation_id="v1_search_files",
        summary="Search files recursively",
        description=(
            "Search for files and directories by name across the entire storage "
            "or starting from a specific path. Uses case-insensitive substring matching."
        ),
        parameters=[
            OpenApiParameter(
                name="q",
                type=str,
                required=True,
                description="Search term (case-insensitive contains match on filename)",
            ),
            OpenApiParameter(
                name="path",
                type=str,
                required=False,
                description="Starting directory for recursive search (default: root)",
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                required=False,
                description=f"Max results to return (default {DEFAULT_LIMIT}, max {MAX_LIMIT})",
            ),
        ],
        responses={
            200: OpenApiResponse(description="Search results"),
            400: OpenApiResponse(description="Invalid request"),
        },
        tags=["Files"],
    )
    def get(self, request: Request) -> Response:
        """Search files recursively."""
        # Get and validate query param
        query = request.query_params.get("q", "").strip()
        if not query:
            return Response(
                {"error": {"code": "MISSING_QUERY", "message": "Query parameter 'q' is required"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get search path
        search_path = request.query_params.get("path", "").strip()
        if search_path:
            try:
                search_path = normalize_path(search_path)
            except PathValidationError as e:
                return Response(
                    {"error": {"code": "INVALID_PATH", "message": str(e), "path": search_path}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Get and validate limit
        try:
            limit = int(request.query_params.get("limit", DEFAULT_LIMIT))
            limit = max(1, min(limit, MAX_LIMIT))
        except ValueError:
            limit = DEFAULT_LIMIT

        # Get user storage root
        user_root = get_user_storage_path(request.user)
        backend = LocalStorageBackend()
        storage_root = backend.storage_root / user_root

        # Build full search path
        if search_path:
            full_search_path = storage_root / search_path
        else:
            full_search_path = storage_root

        # Validate search path exists and is within user's storage
        real_search = full_search_path.resolve()
        real_root = storage_root.resolve()

        if not str(real_search).startswith(str(real_root)):
            return Response(
                {"error": {"code": "INVALID_PATH", "message": "Path traversal not allowed"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not full_search_path.exists():
            return Response(
                {
                    "error": {
                        "code": "PATH_NOT_FOUND",
                        "message": f"Path '{search_path or '/'}' does not exist",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if not full_search_path.is_dir():
            return Response(
                {"error": {"code": "PATH_IS_FILE", "message": "Search path must be a directory"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Perform recursive search
        results = []
        query_lower = query.lower()
        truncated = False

        for root, dirs, files in os.walk(str(full_search_path)):
            root_path = Path(root)

            # Check directories
            for dir_name in dirs:
                if query_lower in dir_name.lower():
                    if len(results) >= limit:
                        truncated = True
                        break
                    dir_path = root_path / dir_name
                    rel_path = str(dir_path.relative_to(storage_root))
                    results.append({
                        "name": dir_name,
                        "path": rel_path,
                        "type": "directory",
                    })

            if truncated:
                break

            # Check files
            for file_name in files:
                if query_lower in file_name.lower():
                    if len(results) >= limit:
                        truncated = True
                        break
                    file_path = root_path / file_name
                    rel_path = str(file_path.relative_to(storage_root))
                    stat = file_path.stat()
                    results.append({
                        "name": file_name,
                        "path": rel_path,
                        "type": "file",
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(
                            stat.st_mtime, tz=dt_timezone.utc
                        ).isoformat(),
                    })

            if truncated:
                break

        return Response({
            "results": results,
            "count": len(results),
            "truncated": truncated,
            "search_path": f"/{search_path}" if search_path else "/",
        })


class AdminSearchFilesView(StormCloudBaseAPIView):
    """Recursive file search for admins on any user's files."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        operation_id="v1_admin_search_files",
        summary="Search user's files recursively (Admin)",
        description=(
            "Search for files and directories by name across a user's entire storage "
            "or starting from a specific path. Uses case-insensitive substring matching."
        ),
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                location=OpenApiParameter.PATH,
                description="Target user ID",
            ),
            OpenApiParameter(
                name="q",
                type=str,
                required=True,
                description="Search term (case-insensitive contains match on filename)",
            ),
            OpenApiParameter(
                name="path",
                type=str,
                required=False,
                description="Starting directory for recursive search (default: root)",
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                required=False,
                description=f"Max results to return (default {DEFAULT_LIMIT}, max {MAX_LIMIT})",
            ),
        ],
        responses={
            200: OpenApiResponse(description="Search results"),
            400: OpenApiResponse(description="Invalid request"),
            404: OpenApiResponse(description="User or path not found"),
        },
        tags=["Admin - Files"],
    )
    def get(self, request: Request, user_id: int) -> Response:
        """Search user's files recursively."""
        # Get target user
        target_user = get_object_or_404(User, pk=user_id)

        # Get and validate query param
        query = request.query_params.get("q", "").strip()
        if not query:
            return Response(
                {"error": {"code": "MISSING_QUERY", "message": "Query parameter 'q' is required"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get search path
        search_path = request.query_params.get("path", "").strip()
        if search_path:
            try:
                search_path = normalize_path(search_path)
            except PathValidationError as e:
                return Response(
                    {"error": {"code": "INVALID_PATH", "message": str(e), "path": search_path}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Get and validate limit
        try:
            limit = int(request.query_params.get("limit", DEFAULT_LIMIT))
            limit = max(1, min(limit, MAX_LIMIT))
        except ValueError:
            limit = DEFAULT_LIMIT

        # Get user storage root (admin accessing target user's files)
        user_root = str(target_user.id)
        backend = LocalStorageBackend()
        storage_root = backend.storage_root / user_root

        # Build full search path
        if search_path:
            full_search_path = storage_root / search_path
        else:
            full_search_path = storage_root

        # Validate search path exists and is within user's storage
        real_search = full_search_path.resolve()
        real_root = storage_root.resolve()

        if not str(real_search).startswith(str(real_root)):
            return Response(
                {"error": {"code": "INVALID_PATH", "message": "Path traversal not allowed"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # If storage root doesn't exist, create it (like other admin endpoints)
        if not storage_root.exists():
            storage_root.mkdir(parents=True, exist_ok=True)

        if not full_search_path.exists():
            return Response(
                {
                    "error": {
                        "code": "PATH_NOT_FOUND",
                        "message": f"Path '{search_path or '/'}' does not exist",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if not full_search_path.is_dir():
            return Response(
                {"error": {"code": "PATH_IS_FILE", "message": "Search path must be a directory"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Perform recursive search
        results = []
        query_lower = query.lower()
        truncated = False

        for root, dirs, files in os.walk(str(full_search_path)):
            root_path = Path(root)

            # Check directories
            for dir_name in dirs:
                if query_lower in dir_name.lower():
                    if len(results) >= limit:
                        truncated = True
                        break
                    dir_path = root_path / dir_name
                    rel_path = str(dir_path.relative_to(storage_root))
                    results.append({
                        "name": dir_name,
                        "path": rel_path,
                        "type": "directory",
                    })

            if truncated:
                break

            # Check files
            for file_name in files:
                if query_lower in file_name.lower():
                    if len(results) >= limit:
                        truncated = True
                        break
                    file_path = root_path / file_name
                    rel_path = str(file_path.relative_to(storage_root))
                    stat = file_path.stat()
                    results.append({
                        "name": file_name,
                        "path": rel_path,
                        "type": "file",
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(
                            stat.st_mtime, tz=dt_timezone.utc
                        ).isoformat(),
                    })

            if truncated:
                break

        return Response({
            "results": results,
            "count": len(results),
            "truncated": truncated,
            "search_path": f"/{search_path}" if search_path else "/",
            "target_user": {"id": target_user.id, "username": target_user.username},
        })
