"""API views for CMS app (stub for Phase 1)."""

from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema

from core.views import StormCloudBaseAPIView
from .serializers import ManagedContentSerializer


class ManagedContentListView(StormCloudBaseAPIView):
    """List managed content."""

    @extend_schema(
        summary="List managed content",
        description="List all files under CMS management. NOT IMPLEMENTED in Phase 1.",
        responses={501: None},
        tags=['CMS']
    )
    def get(self, request):
        """List managed content."""
        return Response(
            {
                "error": {
                    "code": "NOT_IMPLEMENTED",
                    "message": "CMS functionality not implemented in Phase 1.",
                }
            },
            status=status.HTTP_501_NOT_IMPLEMENTED
        )


class ManagedContentAddView(StormCloudBaseAPIView):
    """Add file(s) to CMS management."""

    @extend_schema(
        summary="Add to CMS",
        description="Mark files for CMS management. NOT IMPLEMENTED in Phase 1.",
        responses={501: None},
        tags=['CMS']
    )
    def post(self, request):
        """Add to CMS."""
        return Response(
            {
                "error": {
                    "code": "NOT_IMPLEMENTED",
                    "message": "CMS functionality not implemented in Phase 1.",
                }
            },
            status=status.HTTP_501_NOT_IMPLEMENTED
        )


class ManagedContentRemoveView(StormCloudBaseAPIView):
    """Remove file from CMS management."""

    @extend_schema(
        summary="Remove from CMS",
        description="Remove file from CMS management. NOT IMPLEMENTED in Phase 1.",
        responses={501: None},
        tags=['CMS']
    )
    def delete(self, request, content_id):
        """Remove from CMS."""
        return Response(
            {
                "error": {
                    "code": "NOT_IMPLEMENTED",
                    "message": "CMS functionality not implemented in Phase 1.",
                }
            },
            status=status.HTTP_501_NOT_IMPLEMENTED
        )


class ManagedContentRenderView(StormCloudBaseAPIView):
    """Render managed content."""

    @extend_schema(
        summary="Render content",
        description="Render markdown content with Spellbook. NOT IMPLEMENTED in Phase 1.",
        responses={501: None},
        tags=['CMS']
    )
    def post(self, request, content_id=None):
        """Render content."""
        return Response(
            {
                "error": {
                    "code": "NOT_IMPLEMENTED",
                    "message": "CMS rendering not implemented in Phase 1.",
                }
            },
            status=status.HTTP_501_NOT_IMPLEMENTED
        )
