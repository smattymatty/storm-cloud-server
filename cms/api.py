"""API views for CMS page-file mapping."""

from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Max, Min
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status
from rest_framework.response import Response

from core.views import StormCloudBaseAPIView

from .models import PageFileMapping
from .serializers import (
    MappingReportSerializer,
    PageSummarySerializer,
    PageDetailSerializer,
    FileDetailSerializer,
)


class MappingReportView(StormCloudBaseAPIView):
    """
    POST /api/v1/cms/mappings/report/

    Receive page→files mapping from Glue middleware.
    Creates or updates PageFileMapping records.
    """

    @extend_schema(
        summary="Report page-file mapping",
        description=(
            "Receive page→files mapping from Storm Cloud Glue middleware. "
            "Creates or updates PageFileMapping records for the authenticated user."
        ),
        request=MappingReportSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "page_path": {"type": "string"},
                    "created": {"type": "integer"},
                    "updated": {"type": "integer"},
                },
            },
        },
        tags=["CMS"],
    )
    def post(self, request):
        serializer = MappingReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        page_path = serializer.validated_data["page_path"]
        file_paths = serializer.validated_data["file_paths"]
        owner = request.user

        # Normalize page_path to have leading slash
        if not page_path.startswith("/"):
            page_path = f"/{page_path}"

        created_count = 0
        updated_count = 0

        with transaction.atomic():
            for file_path in file_paths:
                mapping, created = PageFileMapping.objects.update_or_create(
                    owner=owner,
                    page_path=page_path,
                    file_path=file_path,
                    defaults={"last_seen": timezone.now()},
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1

        return Response(
            {
                "status": "ok",
                "page_path": page_path,
                "created": created_count,
                "updated": updated_count,
            },
            status=status.HTTP_200_OK,
        )


class PageListView(StormCloudBaseAPIView):
    """
    GET /api/v1/cms/pages/

    List all pages with content mappings for the authenticated user.
    """

    @extend_schema(
        summary="List pages with content",
        description=(
            "List all pages with content mappings. "
            "Returns page paths with file counts and staleness info."
        ),
        parameters=[
            OpenApiParameter(
                name="stale",
                type=str,
                description="Set to 'true' to show only stale pages (not seen in 24h)",
            ),
            OpenApiParameter(
                name="sort",
                type=str,
                description="Sort by: 'path', 'last_seen', 'file_count' (default: last_seen)",
            ),
            OpenApiParameter(
                name="order",
                type=str,
                description="Sort order: 'asc' or 'desc' (default: desc)",
            ),
        ],
        responses={200: PageSummarySerializer(many=True)},
        tags=["CMS"],
    )
    def get(self, request):
        owner = request.user
        threshold = timezone.now() - timedelta(hours=24)

        # Aggregate by page_path
        pages = (
            PageFileMapping.objects.filter(owner=owner)
            .values("page_path")
            .annotate(
                file_count=Count("id"),
                first_seen=Min("first_seen"),
                last_seen=Max("last_seen"),
            )
        )

        # Filter stale if requested
        show_stale_only = request.query_params.get("stale", "").lower() == "true"

        if show_stale_only:
            pages = pages.filter(last_seen__lt=threshold)

        # Sort
        sort_field = request.query_params.get("sort", "last_seen")
        sort_order = request.query_params.get("order", "desc")

        sort_map = {
            "path": "page_path",
            "last_seen": "last_seen",
            "file_count": "file_count",
        }
        order_by = sort_map.get(sort_field, "last_seen")
        if sort_order == "desc":
            order_by = f"-{order_by}"

        pages = pages.order_by(order_by)

        # Build response
        result = []
        stale_count = 0

        for page in pages:
            is_stale = page["last_seen"] < threshold
            if is_stale:
                stale_count += 1
                staleness_hours = int(
                    (timezone.now() - page["last_seen"]).total_seconds() / 3600
                )
            else:
                staleness_hours = None

            result.append(
                {
                    "page_path": page["page_path"],
                    "file_count": page["file_count"],
                    "first_seen": page["first_seen"],
                    "last_seen": page["last_seen"],
                    "is_stale": is_stale,
                    "staleness_hours": staleness_hours,
                }
            )

        return Response(
            {
                "pages": result,
                "total": len(result),
                "stale_count": stale_count,
            }
        )


class PageDetailView(StormCloudBaseAPIView):
    """
    GET /api/v1/cms/pages/<path>/
    DELETE /api/v1/cms/pages/<path>/

    Get files used on a page, or delete all mappings for a page.
    """

    @extend_schema(
        summary="Get files for a page",
        description="Get all content files used on a specific page.",
        responses={200: PageDetailSerializer},
        tags=["CMS"],
    )
    def get(self, request, page_path: str):
        # Ensure leading slash
        if not page_path.startswith("/"):
            page_path = f"/{page_path}"

        owner = request.user
        threshold = timezone.now() - timedelta(hours=24)

        mappings = PageFileMapping.objects.filter(
            owner=owner, page_path=page_path
        ).order_by("-last_seen")

        if not mappings.exists():
            return Response(
                {"error": f"No mappings found for page: {page_path}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        files = []
        page_first_seen = None
        page_last_seen = None

        for mapping in mappings:
            is_stale = mapping.last_seen < threshold
            staleness_hours = mapping.staleness_hours

            files.append(
                {
                    "file_path": mapping.file_path,
                    "first_seen": mapping.first_seen,
                    "last_seen": mapping.last_seen,
                    "is_stale": is_stale,
                    "staleness_hours": staleness_hours,
                }
            )

            if page_first_seen is None or mapping.first_seen < page_first_seen:
                page_first_seen = mapping.first_seen
            if page_last_seen is None or mapping.last_seen > page_last_seen:
                page_last_seen = mapping.last_seen

        return Response(
            {
                "page_path": page_path,
                "files": files,
                "first_seen": page_first_seen,
                "last_seen": page_last_seen,
                "is_stale": page_last_seen < threshold,
            }
        )

    @extend_schema(
        summary="Delete page mappings",
        description="Delete all mappings for a page (manual cleanup).",
        responses={
            200: {
                "type": "object",
                "properties": {
                    "deleted": {"type": "integer"},
                    "page_path": {"type": "string"},
                },
            },
        },
        tags=["CMS"],
    )
    def delete(self, request, page_path: str):
        if not page_path.startswith("/"):
            page_path = f"/{page_path}"

        owner = request.user

        deleted, _ = PageFileMapping.objects.filter(
            owner=owner, page_path=page_path
        ).delete()

        if deleted == 0:
            return Response(
                {"error": f"No mappings found for page: {page_path}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "deleted": deleted,
                "page_path": page_path,
            }
        )


class FileDetailView(StormCloudBaseAPIView):
    """
    GET /api/v1/cms/files/<path>/pages/

    Get all pages that use a specific file.
    """

    @extend_schema(
        summary="Get pages using a file",
        description="Get all pages that use a specific content file.",
        responses={200: FileDetailSerializer},
        tags=["CMS"],
    )
    def get(self, request, file_path: str):
        owner = request.user
        threshold = timezone.now() - timedelta(hours=24)

        mappings = PageFileMapping.objects.filter(
            owner=owner, file_path=file_path
        ).order_by("-last_seen")

        if not mappings.exists():
            return Response(
                {"error": f"No mappings found for file: {file_path}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        pages = []
        for mapping in mappings:
            pages.append(
                {
                    "page_path": mapping.page_path,
                    "first_seen": mapping.first_seen,
                    "last_seen": mapping.last_seen,
                    "is_stale": mapping.last_seen < threshold,
                }
            )

        return Response(
            {
                "file_path": file_path,
                "pages": pages,
                "page_count": len(pages),
            }
        )


class StaleCleanupView(StormCloudBaseAPIView):
    """
    POST /api/v1/cms/cleanup/

    Delete stale mappings (not seen in X hours).
    """

    @extend_schema(
        summary="Cleanup stale mappings",
        description=(
            "Delete mappings not seen in X hours. "
            "Default threshold is 168 hours (7 days). Minimum is 24 hours."
        ),
        request={
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Delete mappings not seen in X hours (default: 168, min: 24)",
                },
            },
        },
        responses={
            200: {
                "type": "object",
                "properties": {
                    "deleted": {"type": "integer"},
                    "threshold_hours": {"type": "integer"},
                },
            },
        },
        tags=["CMS"],
    )
    def post(self, request):
        hours = request.data.get("hours", 168)

        try:
            hours = int(hours)
            if hours < 24:
                return Response(
                    {"error": "Minimum threshold is 24 hours"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except (TypeError, ValueError):
            return Response(
                {"error": "hours must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deleted = PageFileMapping.cleanup_stale(request.user, hours=hours)

        return Response(
            {
                "deleted": deleted,
                "threshold_hours": hours,
            }
        )
