"""URL configuration for CMS app."""

from django.urls import path, re_path

from . import api

app_name = "cms"

urlpatterns = [
    # Mapping report (from Glue middleware)
    path("mappings/report/", api.MappingReportView.as_view(), name="mapping-report"),
    # Pages list
    path("pages/", api.PageListView.as_view(), name="page-list"),
    # Page detail and delete (path can contain slashes)
    re_path(
        r"^pages/(?P<page_path>.+)/$",
        api.PageDetailView.as_view(),
        name="page-detail",
    ),
    # File detail - pages using this file (path can contain slashes)
    re_path(
        r"^files/(?P<file_path>.+)/pages/$",
        api.FileDetailView.as_view(),
        name="file-pages",
    ),
    # Cleanup stale mappings
    path("cleanup/", api.StaleCleanupView.as_view(), name="cleanup"),
    # Markdown preview (Django Spellbook rendering)
    path("preview/", api.MarkdownPreviewView.as_view(), name="markdown-preview"),
    # ==========================================================================
    # Content Flags
    # ==========================================================================
    # Flag list and pending review (static routes first)
    path("flags/", api.FlagListView.as_view(), name="flag-list"),
    path("flags/pending/", api.PendingReviewView.as_view(), name="pending-review"),
    # File flags - history must come before set to avoid matching {flag_type}="history"
    re_path(
        r"^files/(?P<path>.+)/flags/(?P<flag_type>[a-z_]+)/history/$",
        api.FlagHistoryView.as_view(),
        name="flag-history",
    ),
    re_path(
        r"^files/(?P<path>.+)/flags/(?P<flag_type>[a-z_]+)/$",
        api.SetFlagView.as_view(),
        name="set-flag",
    ),
    re_path(
        r"^files/(?P<path>.+)/flags/$",
        api.FileFlagsView.as_view(),
        name="file-flags",
    ),
]
