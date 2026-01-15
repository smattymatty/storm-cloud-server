"""Admin API views for CMS operations on user content.

These endpoints allow admins to browse and manage any user's CMS data
(pages, flags, mappings) while maintaining audit trail via ContentFlagHistory.
"""

from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

from django.contrib.auth import get_user_model
from django.db.models import Count, Max, Min, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response

from core.views import StormCloudBaseAPIView
from storage.models import StoredFile

from .api import get_user_from_request
from .models import ContentFlag, PageFileMapping, PageStats
from .serializers import (
    ContentFlagSerializer,
    FlagHistorySerializer,
    SetFlagSerializer,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser as User
else:
    User = get_user_model()


def _target_user_response(target_user: User) -> dict[str, Any]:
    """Build target_user context for responses."""
    return {
        "id": target_user.id,
        "username": target_user.username,
    }


class AdminCmsBaseView(StormCloudBaseAPIView):
    """Base view for admin CMS operations."""

    permission_classes = [IsAdminUser]

    def get_target_user(self, user_id: int) -> User:
        """Get the target user whose CMS we're operating on."""
        return get_object_or_404(User, pk=user_id)


# =============================================================================
# Page Views
# =============================================================================


class AdminPageListView(AdminCmsBaseView):
    """
    GET /api/v1/admin/users/<user_id>/cms/pages/

    List all pages with content mappings for a user (admin).
    """

    @extend_schema(
        summary="List user's CMS pages (Admin)",
        description="List all pages with content mappings for a specific user.",
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                location=OpenApiParameter.PATH,
                description="Target user ID",
            ),
            OpenApiParameter(
                name="stale",
                type=str,
                description="Set to 'true' to show only stale pages (not seen in 24h)",
            ),
            OpenApiParameter(
                name="sort",
                type=str,
                description="Sort by: 'path', 'last_seen', 'file_count', 'views' (default: last_seen)",
            ),
            OpenApiParameter(
                name="order",
                type=str,
                description="Sort order: 'asc' or 'desc' (default: desc)",
            ),
            OpenApiParameter(
                name="search",
                type=str,
                description="Filter pages by path (case-insensitive contains)",
            ),
        ],
        responses={200: dict},
        tags=["Admin - CMS"],
    )
    def get(self, request: Request, user_id: int) -> Response:
        target_user = self.get_target_user(user_id)
        threshold = timezone.now() - timedelta(hours=24)

        # Build filter with optional search
        base_filter = Q(owner=target_user)
        search = request.query_params.get("search", "").strip()
        if search:
            base_filter &= Q(page_path__icontains=search)

        # Aggregate by page_path
        pages = (
            PageFileMapping.objects.filter(base_filter)
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
            "views": "view_count",
        }

        # Get view counts for all pages
        stats_map = {
            s.page_path: s.view_count
            for s in PageStats.objects.filter(owner=target_user)
        }

        # Sort pages
        pages_list: list[dict[str, Any]] = list(pages)
        if sort_field == "views":
            pages_list.sort(
                key=lambda p: stats_map.get(p["page_path"], 0),
                reverse=(sort_order == "desc"),
            )
        else:
            pages_list = sorted(
                pages_list,
                key=lambda p: p[sort_map.get(sort_field, "last_seen")],
                reverse=(sort_order == "desc"),
            )

        # Build response
        result = []
        stale_count = 0

        for page in pages_list:
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
                    "view_count": stats_map.get(page["page_path"], 0),
                }
            )

        return Response(
            {
                "pages": result,
                "total": len(result),
                "stale_count": stale_count,
                "target_user": _target_user_response(target_user),
            }
        )


class AdminPageDetailView(AdminCmsBaseView):
    """
    GET /api/v1/admin/users/<user_id>/cms/pages/<path>/
    DELETE /api/v1/admin/users/<user_id>/cms/pages/<path>/

    Get files used on a page, or delete all mappings for a page (admin).
    """

    @extend_schema(
        summary="Get files for a user's page (Admin)",
        description="Get all content files used on a specific page for a user.",
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                location=OpenApiParameter.PATH,
                description="Target user ID",
            ),
        ],
        responses={200: dict},
        tags=["Admin - CMS"],
    )
    def get(self, request: Request, user_id: int, page_path: str) -> Response:
        target_user = self.get_target_user(user_id)

        # Ensure leading slash
        if not page_path.startswith("/"):
            page_path = f"/{page_path}"

        threshold = timezone.now() - timedelta(hours=24)

        mappings = PageFileMapping.objects.filter(
            owner=target_user, page_path=page_path
        ).order_by("-last_seen")

        if not mappings.exists():
            return Response(
                {
                    "error": f"No mappings found for page: {page_path}",
                    "target_user": _target_user_response(target_user),
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Collect file paths and prefetch StoredFiles with their flags
        file_paths = [m.file_path for m in mappings]
        stored_files = StoredFile.objects.filter(
            owner=target_user.account, path__in=file_paths
        ).prefetch_related("content_flags")
        stored_file_map = {sf.path: sf for sf in stored_files}

        files = []
        page_first_seen = None
        page_last_seen = None

        for mapping in mappings:
            is_stale = mapping.last_seen < threshold
            staleness_hours = mapping.staleness_hours

            # Get flags for this file
            file_flags = {}
            stored_file = stored_file_map.get(mapping.file_path)
            if stored_file:
                for flag in stored_file.content_flags.all():
                    file_flags[flag.flag_type] = flag.is_active

            files.append(
                {
                    "file_path": mapping.file_path,
                    "first_seen": mapping.first_seen,
                    "last_seen": mapping.last_seen,
                    "is_stale": is_stale,
                    "staleness_hours": staleness_hours,
                    "flags": {
                        "ai_generated": file_flags.get("ai_generated", False),
                        "user_approved": file_flags.get("user_approved", False),
                    },
                }
            )

            if page_first_seen is None or mapping.first_seen < page_first_seen:
                page_first_seen = mapping.first_seen
            if page_last_seen is None or mapping.last_seen > page_last_seen:
                page_last_seen = mapping.last_seen

        # Get view count
        try:
            stats = PageStats.objects.get(owner=target_user, page_path=page_path)
            view_count = stats.view_count
        except PageStats.DoesNotExist:
            view_count = 0

        return Response(
            {
                "page_path": page_path,
                "files": files,
                "first_seen": page_first_seen,
                "last_seen": page_last_seen,
                "is_stale": page_last_seen is not None and page_last_seen < threshold,
                "view_count": view_count,
                "target_user": _target_user_response(target_user),
            }
        )

    @extend_schema(
        summary="Delete user's page mappings (Admin)",
        description="Delete all mappings for a page (manual cleanup) for a user.",
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                location=OpenApiParameter.PATH,
                description="Target user ID",
            ),
        ],
        responses={200: dict},
        tags=["Admin - CMS"],
    )
    def delete(self, request: Request, user_id: int, page_path: str) -> Response:
        target_user = self.get_target_user(user_id)

        if not page_path.startswith("/"):
            page_path = f"/{page_path}"

        deleted, _ = PageFileMapping.objects.filter(
            owner=target_user, page_path=page_path
        ).delete()

        if deleted == 0:
            return Response(
                {
                    "error": f"No mappings found for page: {page_path}",
                    "target_user": _target_user_response(target_user),
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "deleted": deleted,
                "page_path": page_path,
                "target_user": _target_user_response(target_user),
            }
        )


class AdminPageFlagsView(AdminCmsBaseView):
    """
    GET /api/v1/admin/users/<user_id>/cms/pages/flags/

    Get aggregated flag counts per page for a user (admin).
    """

    @extend_schema(
        summary="Get flag counts per page (Admin)",
        description="Returns aggregated content flag counts for each page of a user.",
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                location=OpenApiParameter.PATH,
                description="Target user ID",
            ),
        ],
        responses={200: dict},
        tags=["Admin - CMS"],
    )
    def get(self, request: Request, user_id: int) -> Response:
        target_user = self.get_target_user(user_id)

        # Get all pages for this user
        pages = PageFileMapping.objects.filter(
            owner=target_user
        ).values("page_path").distinct()

        result = []
        for page in pages:
            page_path = page["page_path"]

            # Get file paths on this page
            file_paths = PageFileMapping.objects.filter(
                owner=target_user,
                page_path=page_path
            ).values_list("file_path", flat=True)

            # Count active flags on those files
            ai_count = ContentFlag.objects.filter(
                stored_file__owner=target_user.account,
                stored_file__path__in=file_paths,
                flag_type="ai_generated",
                is_active=True
            ).count()

            approved_count = ContentFlag.objects.filter(
                stored_file__owner=target_user.account,
                stored_file__path__in=file_paths,
                flag_type="user_approved",
                is_active=True
            ).count()

            result.append({
                "page_path": page_path,
                "flags": {
                    "ai_generated": ai_count,
                    "user_approved": approved_count,
                }
            })

        return Response({
            "pages": result,
            "target_user": _target_user_response(target_user),
        })


# =============================================================================
# Flag Views
# =============================================================================


class AdminFlagListView(AdminCmsBaseView):
    """
    GET /api/v1/admin/users/<user_id>/cms/flags/

    List user's files with flags (admin).
    """

    @extend_schema(
        summary="List user's files with flags (Admin)",
        description="List all files that have any flags for a specific user.",
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                location=OpenApiParameter.PATH,
                description="Target user ID",
            ),
            OpenApiParameter(
                name="ai_generated",
                type=str,
                description="Filter by ai_generated flag: 'true' or 'false'",
            ),
            OpenApiParameter(
                name="user_approved",
                type=str,
                description="Filter by user_approved flag: 'true' or 'false'",
            ),
            OpenApiParameter(
                name="needs_review",
                type=str,
                description="Set to 'true' to show only files needing review",
            ),
        ],
        responses={200: dict},
        tags=["Admin - CMS"],
    )
    def get(self, request: Request, user_id: int) -> Response:
        target_user = self.get_target_user(user_id)

        # Get query parameters
        ai_generated_filter = request.query_params.get("ai_generated")
        user_approved_filter = request.query_params.get("user_approved")
        needs_review_filter = request.query_params.get("needs_review", "").lower() == "true"

        # Get all files for this user that have any flags
        files_with_flags = StoredFile.objects.filter(
            owner=target_user.account,
            content_flags__isnull=False,
        ).distinct()

        result = []
        for stored_file in files_with_flags:
            # Get flag status
            ai_flag = stored_file.content_flags.filter(flag_type="ai_generated").first()
            approved_flag = stored_file.content_flags.filter(flag_type="user_approved").first()

            ai_generated = ai_flag.is_active if ai_flag else None
            user_approved = approved_flag.is_active if approved_flag else None
            needs_review = (ai_generated is True) and (user_approved is not True)

            # Get last flag change time
            last_flag = stored_file.content_flags.order_by("-changed_at").first()
            last_flag_change = last_flag.changed_at if last_flag else None

            # Apply filters
            if ai_generated_filter is not None:
                filter_val = ai_generated_filter.lower() == "true"
                if ai_generated != filter_val:
                    continue

            if user_approved_filter is not None:
                filter_val = user_approved_filter.lower() == "true"
                if user_approved != filter_val:
                    continue

            if needs_review_filter and not needs_review:
                continue

            result.append(
                {
                    "file_path": stored_file.path,
                    "file_name": stored_file.name,
                    "ai_generated": ai_generated,
                    "user_approved": user_approved,
                    "needs_review": needs_review,
                    "last_flag_change": last_flag_change,
                }
            )

        return Response(
            {
                "count": len(result),
                "files": result,
                "target_user": _target_user_response(target_user),
            }
        )


class AdminPendingReviewView(AdminCmsBaseView):
    """
    GET /api/v1/admin/users/<user_id>/cms/flags/pending/

    User's files that need review (ai_generated but not user_approved) (admin).
    """

    @extend_schema(
        summary="List user's files pending review (Admin)",
        description="Get files that need review for a user: ai_generated=true AND user_approved!=true.",
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                location=OpenApiParameter.PATH,
                description="Target user ID",
            ),
        ],
        responses={200: dict},
        tags=["Admin - CMS"],
    )
    def get(self, request: Request, user_id: int) -> Response:
        target_user = self.get_target_user(user_id)

        # Files with ai_generated=True
        ai_generated_files = ContentFlag.objects.filter(
            stored_file__owner=target_user.account,
            flag_type="ai_generated",
            is_active=True,
        ).values_list("stored_file_id", flat=True)

        # Files with user_approved=True
        approved_files = ContentFlag.objects.filter(
            stored_file__owner=target_user.account,
            flag_type="user_approved",
            is_active=True,
        ).values_list("stored_file_id", flat=True)

        # Pending = AI generated but not approved
        pending_file_ids = set(ai_generated_files) - set(approved_files)

        files = StoredFile.objects.filter(id__in=pending_file_ids)

        result = []
        for stored_file in files:
            ai_flag = stored_file.content_flags.filter(flag_type="ai_generated").first()
            result.append(
                {
                    "file_path": stored_file.path,
                    "file_name": stored_file.name,
                    "ai_generated": True,
                    "user_approved": False,
                    "needs_review": True,
                    "last_flag_change": ai_flag.changed_at if ai_flag else None,
                }
            )

        return Response(
            {
                "count": len(result),
                "files": result,
                "target_user": _target_user_response(target_user),
            }
        )


class AdminFileFlagsView(AdminCmsBaseView):
    """
    GET /api/v1/admin/users/<user_id>/cms/files/<path>/flags/

    Get all flags for a user's file (admin).
    """

    @extend_schema(
        summary="Get all flags for a user's file (Admin)",
        description="Get all flags for a file owned by a specific user.",
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                location=OpenApiParameter.PATH,
                description="Target user ID",
            ),
        ],
        responses={200: dict},
        tags=["Admin - CMS"],
    )
    def get(self, request: Request, user_id: int, file_path: str) -> Response:
        target_user = self.get_target_user(user_id)

        # Find the file owned by the target user
        try:
            stored_file = StoredFile.objects.get(owner=target_user.account, path=file_path)
        except StoredFile.DoesNotExist:
            return Response(
                {
                    "error": {"code": "FILE_NOT_FOUND", "message": f"File not found: {file_path}"},
                    "target_user": _target_user_response(target_user),
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        flags = ContentFlag.objects.filter(stored_file=stored_file)

        # Build response with all flag types (even if not set)
        flag_data: dict[str, Any] = {}
        for flag in flags:
            flag_data[flag.flag_type] = ContentFlagSerializer(flag).data

        # Include inactive/unset flags
        for flag_type, _ in ContentFlag.FlagType.choices:
            if flag_type not in flag_data:
                flag_data[flag_type] = {
                    "flag_type": flag_type,
                    "is_active": False,
                    "metadata": {},
                    "changed_by_username": None,
                    "changed_at": None,
                }

        return Response(
            {
                "file_path": stored_file.path,
                "flags": list(flag_data.values()),
                "target_user": _target_user_response(target_user),
            }
        )


class AdminSetFlagView(AdminCmsBaseView):
    """
    PUT /api/v1/admin/users/<user_id>/cms/files/<path>/flags/<flag_type>/

    Set a specific flag on a user's file (admin).
    """

    @extend_schema(
        summary="Set a flag on a user's file (Admin)",
        description=(
            "Set a specific flag on a file owned by a user. "
            "The admin is recorded as changed_by for audit trail."
        ),
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                location=OpenApiParameter.PATH,
                description="Target user ID",
            ),
        ],
        request=SetFlagSerializer,
        responses={200: ContentFlagSerializer},
        tags=["Admin - CMS"],
    )
    def put(self, request: Request, user_id: int, file_path: str, flag_type: str) -> Response:
        target_user = self.get_target_user(user_id)

        # Validate flag_type
        valid_types = [t[0] for t in ContentFlag.FlagType.choices]
        if flag_type not in valid_types:
            return Response(
                {
                    "error": {
                        "code": "INVALID_FLAG_TYPE",
                        "message": f"Invalid flag type. Must be one of: {valid_types}",
                    },
                    "target_user": _target_user_response(target_user),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Find the file owned by the target user
        try:
            stored_file = StoredFile.objects.get(owner=target_user.account, path=file_path)
        except StoredFile.DoesNotExist:
            return Response(
                {
                    "error": {"code": "FILE_NOT_FOUND", "message": f"File not found: {file_path}"},
                    "target_user": _target_user_response(target_user),
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = SetFlagSerializer(data=request.data, context={"flag_type": flag_type})
        serializer.is_valid(raise_exception=True)

        # Admin is recorded as changed_by (audit trail)
        flag, created = ContentFlag.objects.get_or_create(
            stored_file=stored_file,
            flag_type=flag_type,
            defaults={
                "is_active": serializer.validated_data["is_active"],
                "metadata": serializer.validated_data.get("metadata", {}),
                "changed_by": get_user_from_request(request),  # Admin, not target_user
            },
        )

        if not created:
            flag.is_active = serializer.validated_data["is_active"]
            flag.metadata = serializer.validated_data.get("metadata", {})
            flag.changed_by = get_user_from_request(request)  # Admin, not target_user
            flag.save()  # Triggers history creation

        response_data = ContentFlagSerializer(flag).data
        response_data["target_user"] = _target_user_response(target_user)

        return Response(response_data)


class AdminFlagHistoryView(AdminCmsBaseView):
    """
    GET /api/v1/admin/users/<user_id>/cms/files/<path>/flags/<flag_type>/history/

    Get history for a specific flag on a user's file (admin).
    """

    @extend_schema(
        summary="Get flag history (Admin)",
        description="Get the change history for a specific flag on a user's file.",
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                location=OpenApiParameter.PATH,
                description="Target user ID",
            ),
        ],
        responses={200: dict},
        tags=["Admin - CMS"],
    )
    def get(self, request: Request, user_id: int, file_path: str, flag_type: str) -> Response:
        target_user = self.get_target_user(user_id)

        # Validate flag_type
        valid_types = [t[0] for t in ContentFlag.FlagType.choices]
        if flag_type not in valid_types:
            return Response(
                {
                    "error": {
                        "code": "INVALID_FLAG_TYPE",
                        "message": f"Invalid flag type. Must be one of: {valid_types}",
                    },
                    "target_user": _target_user_response(target_user),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Find the file owned by the target user
        try:
            stored_file = StoredFile.objects.get(owner=target_user.account, path=file_path)
        except StoredFile.DoesNotExist:
            return Response(
                {
                    "error": {"code": "FILE_NOT_FOUND", "message": f"File not found: {file_path}"},
                    "target_user": _target_user_response(target_user),
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            flag = ContentFlag.objects.get(stored_file=stored_file, flag_type=flag_type)
        except ContentFlag.DoesNotExist:
            return Response(
                {
                    "error": {
                        "code": "FLAG_NOT_FOUND",
                        "message": f"Flag '{flag_type}' not found for file: {file_path}",
                    },
                    "target_user": _target_user_response(target_user),
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        history = flag.history.all()

        return Response(
            {
                "flag_type": flag_type,
                "history": FlagHistorySerializer(history, many=True).data,
                "target_user": _target_user_response(target_user),
            }
        )


# =============================================================================
# Cleanup View
# =============================================================================


class AdminStaleCleanupView(AdminCmsBaseView):
    """
    POST /api/v1/admin/users/<user_id>/cms/cleanup/

    Delete stale mappings for a user (admin).
    """

    @extend_schema(
        summary="Cleanup user's stale mappings (Admin)",
        description=(
            "Delete mappings not seen in X hours for a specific user. "
            "Default threshold is 168 hours (7 days). Minimum is 24 hours."
        ),
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                location=OpenApiParameter.PATH,
                description="Target user ID",
            ),
        ],
        request={
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Delete mappings not seen in X hours (default: 168, min: 24)",
                },
            },
        },
        responses={200: dict},
        tags=["Admin - CMS"],
    )
    def post(self, request: Request, user_id: int) -> Response:
        target_user = self.get_target_user(user_id)

        hours = request.data.get("hours", 168)

        try:
            hours = int(hours)
            if hours < 24:
                return Response(
                    {
                        "error": "Minimum threshold is 24 hours",
                        "target_user": _target_user_response(target_user),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except (TypeError, ValueError):
            return Response(
                {
                    "error": "hours must be an integer",
                    "target_user": _target_user_response(target_user),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        deleted = PageFileMapping.cleanup_stale(target_user, hours=hours)

        return Response(
            {
                "deleted": deleted,
                "threshold_hours": hours,
                "target_user": _target_user_response(target_user),
            }
        )
