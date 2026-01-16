"""URL routing for admin CMS endpoints.

These URLs are included under /api/v1/admin/users/<user_id>/cms/
"""

from django.urls import path

from .admin_api import (
    AdminFlagHistoryView,
    AdminFlagListView,
    AdminFileFlagsView,
    AdminPageDetailView,
    AdminPageFlagsView,
    AdminPageListView,
    AdminPendingReviewView,
    AdminSetFlagView,
    AdminStaleCleanupView,
)

urlpatterns = [
    # Page operations
    path("pages/", AdminPageListView.as_view(), name="admin-cms-pages"),
    path("pages/flags/", AdminPageFlagsView.as_view(), name="admin-cms-pages-flags"),
    path(
        "pages/<path:page_path>/",
        AdminPageDetailView.as_view(),
        name="admin-cms-page-detail",
    ),
    # Flag operations
    path("flags/", AdminFlagListView.as_view(), name="admin-cms-flags"),
    path(
        "flags/pending/",
        AdminPendingReviewView.as_view(),
        name="admin-cms-flags-pending",
    ),
    # File flag operations
    path(
        "files/<path:file_path>/flags/",
        AdminFileFlagsView.as_view(),
        name="admin-cms-file-flags",
    ),
    path(
        "files/<path:file_path>/flags/<str:flag_type>/",
        AdminSetFlagView.as_view(),
        name="admin-cms-set-flag",
    ),
    path(
        "files/<path:file_path>/flags/<str:flag_type>/history/",
        AdminFlagHistoryView.as_view(),
        name="admin-cms-flag-history",
    ),
    # Cleanup
    path("cleanup/", AdminStaleCleanupView.as_view(), name="admin-cms-cleanup"),
]
