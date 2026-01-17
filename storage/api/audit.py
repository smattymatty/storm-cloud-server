"""User audit log views."""

from datetime import datetime

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response

from core.views import StormCloudBaseAPIView
from storage.models import FileAuditLog
from storage.serializers import FileAuditLogSerializer


class UserAuditLogPagination(PageNumberPagination):
    """Pagination for user audit logs."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class UserAuditLogView(StormCloudBaseAPIView):
    """View own file activity (user)."""

    pagination_class = UserAuditLogPagination

    @extend_schema(
        summary="View own file activity",
        description="Query your own file audit logs. Only shows activity for your account.",
        parameters=[
            OpenApiParameter(
                name="action",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter by action type (upload, download, delete, preview, edit, etc.)",
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
                description="Filter by path (contains match, for search)",
            ),
            OpenApiParameter(
                name="exact_path",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter by exact path (for per-file view)",
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
        tags=["Audit"],
    )
    def get(self, request: Request) -> Response:
        """Get current user's audit logs."""
        # Return logs where user is either the actor OR the target
        # This allows users to see admin actions on their files
        queryset = FileAuditLog.objects.filter(
            Q(performed_by=request.user.account) | Q(target_user=request.user.account)
        ).distinct()

        # Apply filters
        action = request.query_params.get("action")
        if action:
            queryset = queryset.filter(action=action)

        success = request.query_params.get("success")
        if success is not None:
            queryset = queryset.filter(success=success.lower() == "true")

        path = request.query_params.get("path")
        if path:
            queryset = queryset.filter(path__icontains=path)

        exact_path = request.query_params.get("exact_path")
        if exact_path:
            queryset = queryset.filter(path=exact_path)

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
