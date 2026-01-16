"""API views for bulk file operations."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.permissions import check_user_permission
from core.storage.local import LocalStorageBackend
from core.views import StormCloudBaseAPIView

from storage.api.utils import emit_user_file_action
from storage.models import FileAuditLog


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
