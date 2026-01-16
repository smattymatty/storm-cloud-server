"""Admin-only storage API views."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response

from core.views import StormCloudBaseAPIView


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
