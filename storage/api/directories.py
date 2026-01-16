"""Directory API views."""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from core.utils import PathValidationError, normalize_path
from core.views import StormCloudBaseAPIView

from storage.models import FileAuditLog, StoredFile
from storage.serializers import DirectoryListResponseSerializer, FileInfoResponseSerializer
from storage.services import DirectoryService

# Import emit_user_file_action from legacy module
from storage.api_legacy import emit_user_file_action


class DirectoryListBaseView(StormCloudBaseAPIView):
    """Base view for listing directory contents with pagination."""

    def list_directory(self, request: Request, dir_path: str = "") -> Response:
        """List directory contents with pagination."""
        service = DirectoryService(request.user.account)

        limit = min(int(request.query_params.get("limit", 50)), 200)
        cursor = request.query_params.get("cursor")
        search = request.query_params.get("search", "").strip() or None

        result = service.list_directory(dir_path, limit=limit, cursor=cursor, search=search)

        if not result.success:
            error_status = status.HTTP_400_BAD_REQUEST
            if result.error_code == "DIRECTORY_NOT_FOUND":
                error_status = status.HTTP_404_NOT_FOUND

            return Response(
                {
                    "error": {
                        "code": result.error_code,
                        "message": result.error_message,
                        "path": dir_path,
                    }
                },
                status=error_status,
            )

        return Response({
            "path": result.path,
            "entries": result.entries,
            "count": result.count,
            "total": result.total,
            "next_cursor": result.next_cursor,
        })


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
            OpenApiParameter(
                "search", str, description="Filter by name (case-insensitive contains)"
            ),
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
            OpenApiParameter(
                "search", str, description="Filter by name (case-insensitive contains)"
            ),
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
        service = DirectoryService(request.user.account)
        result = service.create_directory(dir_path)

        if not result.success:
            error_status = status.HTTP_400_BAD_REQUEST
            if result.error_code == "ALREADY_EXISTS":
                error_status = status.HTTP_409_CONFLICT

            # Log failed directory creation
            emit_user_file_action(
                sender=self.__class__,
                request=request,
                action=FileAuditLog.ACTION_CREATE_DIR,
                path=dir_path,
                success=False,
                error_code=result.error_code,
                error_message=result.error_message,
            )

            return Response(
                {
                    "error": {
                        "code": result.error_code,
                        "message": result.error_message,
                        "path": dir_path,
                    }
                },
                status=error_status,
            )

        # Log successful directory creation
        emit_user_file_action(
            sender=self.__class__,
            request=request,
            action=FileAuditLog.ACTION_CREATE_DIR,
            path=dir_path,
        )

        return Response(result.data, status=status.HTTP_201_CREATED)


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
        from storage.serializers import DirectoryReorderSerializer

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
                owner=request.user.account,
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
            owner=request.user.account,
            parent_path=dir_path,
        ).update(sort_position=None)

        return Response(
            {
                "message": "Order reset to alphabetical",
                "path": dir_path,
                "count": updated,
            }
        )
