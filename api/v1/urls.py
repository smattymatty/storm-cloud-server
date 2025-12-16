"""URL configuration for Storm Cloud API v1."""

import time

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.urls import path

from accounts.api import (
    AdminAPIKeyListView,
    AdminAPIKeyRevokeView,
    AdminUserActivateView,
    # Admin
    AdminUserCreateView,
    AdminUserDeactivateView,
    AdminUserDetailView,
    AdminUserListView,
    AdminUserPasswordResetView,
    AdminUserVerifyView,
    # API Keys
    APIKeyCreateView,
    APIKeyListView,
    APIKeyRevokeView,
    # Account Management
    AuthMeView,
    DeactivateAccountView,
    DeleteAccountView,
    EmailVerificationView,
    # Session Auth
    LoginView,
    LogoutView,
    # Registration & Email Verification
    RegistrationView,
    ResendVerificationView,
)
from cms.api import (
    ManagedContentAddView,
    ManagedContentListView,
    ManagedContentRemoveView,
    ManagedContentRenderBulkView,
    ManagedContentRenderView,
)
from storage.api import (
    DirectoryCreateView,
    DirectoryListRootView,
    DirectoryListView,
    DirectoryReorderView,
    DirectoryResetOrderView,
    FileCreateView,
    FileDeleteView,
    FileDetailView,
    FileDownloadView,
    FileUploadView,
    IndexRebuildView,
    PublicShareDownloadView,
    PublicShareInfoView,
    ShareLinkDetailView,
    ShareLinkListCreateView,
)

# Server start time for uptime calculation
_server_start_time = time.time()


# Health check views (simple, no authentication)
def health_ping(request):
    """Basic health check for Docker healthcheck."""
    return JsonResponse({"status": "ok"})


def health_status(request):
    """Detailed health status with database check and uptime."""
    status_data = {
        "status": "healthy",
        "version": "0.1.0",
        "timestamp": int(time.time()),
    }

    # Calculate uptime
    uptime_seconds = int(time.time() - _server_start_time)
    hours = uptime_seconds // 3600
    minutes = (uptime_seconds % 3600) // 60
    status_data["uptime"] = f"{hours}h {minutes}m"

    # Check database connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        status_data["database"] = "connected"
    except Exception as e:
        status_data["database"] = "error"
        status_data["status"] = "degraded"

    # Storage backend info
    try:
        from core.storage import get_storage_backend

        backend = get_storage_backend()
        status_data["storage"] = backend.__class__.__name__.replace(
            "StorageBackend", ""
        ).lower()
    except:
        status_data["storage"] = "unknown"

    return JsonResponse(status_data)


urlpatterns = [
    # Health (no auth required for Docker healthchecks)
    path("health/", health_ping, name="health"),
    path("health/ping/", health_ping, name="health-ping"),
    path("health/status/", health_status, name="health-status"),
    # =========================================================================
    # Authentication & Authorization
    # =========================================================================
    # Registration & Email Verification
    path("auth/register/", RegistrationView.as_view(), name="auth-register"),
    path(
        "auth/verify-email/", EmailVerificationView.as_view(), name="auth-verify-email"
    ),
    path(
        "auth/resend-verification/",
        ResendVerificationView.as_view(),
        name="auth-resend-verification",
    ),
    # Session Authentication (for Swagger UI)
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    # Current User
    path("auth/me/", AuthMeView.as_view(), name="auth-me"),
    # API Key Management (tokens per spec) - List/Create combined
    path("auth/tokens/", APIKeyListView.as_view(), name="auth-tokens"),
    path(
        "auth/tokens/<uuid:key_id>/revoke/",
        APIKeyRevokeView.as_view(),
        name="auth-tokens-revoke",
    ),
    # Account Management
    path("auth/deactivate/", DeactivateAccountView.as_view(), name="auth-deactivate"),
    path("auth/delete/", DeleteAccountView.as_view(), name="auth-delete"),
    # =========================================================================
    # Admin Endpoints
    # =========================================================================
    # User Management (combined list/create endpoint)
    path("admin/users/", AdminUserListView.as_view(), name="admin-users"),
    path(
        "admin/users/<int:user_id>/",
        AdminUserDetailView.as_view(),
        name="admin-users-detail",
    ),
    path(
        "admin/users/<int:user_id>/verify/",
        AdminUserVerifyView.as_view(),
        name="admin-users-verify",
    ),
    path(
        "admin/users/<int:user_id>/deactivate/",
        AdminUserDeactivateView.as_view(),
        name="admin-users-deactivate",
    ),
    path(
        "admin/users/<int:user_id>/activate/",
        AdminUserActivateView.as_view(),
        name="admin-users-activate",
    ),
    path(
        "admin/users/<int:user_id>/reset-password/",
        AdminUserPasswordResetView.as_view(),
        name="admin-users-reset-password",
    ),
    # API Key Management (Admin)
    path("admin/keys/", AdminAPIKeyListView.as_view(), name="admin-keys-list"),
    path(
        "admin/keys/<uuid:key_id>/revoke/",
        AdminAPIKeyRevokeView.as_view(),
        name="admin-keys-revoke",
    ),
    # =========================================================================
    # Storage
    # =========================================================================
    # Directories (ls operations)
    path("dirs/", DirectoryListRootView.as_view(), name="dir-list-root"),
    # Root directory reorder/reset (must come before <path:> routes)
    path("dirs/reorder/", DirectoryReorderView.as_view(), name="dir-reorder-root"),
    path(
        "dirs/reset-order/",
        DirectoryResetOrderView.as_view(),
        name="dir-reset-order-root",
    ),
    # Path-based directory operations
    path(
        "dirs/<path:dir_path>/create/", DirectoryCreateView.as_view(), name="dir-create"
    ),
    path(
        "dirs/<path:dir_path>/reorder/",
        DirectoryReorderView.as_view(),
        name="dir-reorder",
    ),
    path(
        "dirs/<path:dir_path>/reset-order/",
        DirectoryResetOrderView.as_view(),
        name="dir-reset-order",
    ),
    path(
        "dirs/<path:dir_path>/",
        DirectoryListView.as_view(),
        name="dir-list",
    ),
    # Files (file operations)
    path(
        "files/<path:file_path>/create/", FileCreateView.as_view(), name="file-create"
    ),
    path(
        "files/<path:file_path>/upload/", FileUploadView.as_view(), name="file-upload"
    ),
    path(
        "files/<path:file_path>/download/",
        FileDownloadView.as_view(),
        name="file-download",
    ),
    path(
        "files/<path:file_path>/delete/", FileDeleteView.as_view(), name="file-delete"
    ),
    path("files/<path:file_path>/", FileDetailView.as_view(), name="file-detail"),
    # Index management (admin)
    path("index/rebuild/", IndexRebuildView.as_view(), name="index-rebuild"),
    # CMS
    path("cms/", ManagedContentListView.as_view(), name="cms-list"),
    path("cms/add/", ManagedContentAddView.as_view(), name="cms-add"),
    path(
        "cms/<uuid:content_id>/remove/",
        ManagedContentRemoveView.as_view(),
        name="cms-remove",
    ),
    path(
        "cms/<uuid:content_id>/render/",
        ManagedContentRenderView.as_view(),
        name="cms-render",
    ),
    path("cms/render/", ManagedContentRenderBulkView.as_view(), name="cms-render-bulk"),
    # =========================================================================
    # Share Links
    # =========================================================================
    # Authenticated share link management
    path("shares/", ShareLinkListCreateView.as_view(), name="share-list-create"),
    path("shares/<uuid:share_id>/", ShareLinkDetailView.as_view(), name="share-detail"),
    # Public share access (no auth required)
    path(
        "public/<str:token>/", PublicShareInfoView.as_view(), name="public-share-info"
    ),
    path(
        "public/<str:token>/download/",
        PublicShareDownloadView.as_view(),
        name="public-share-download",
    ),
]

# =============================================================================
# Development-only Sentry test endpoint
# =============================================================================
if settings.DEBUG:

    def sentry_test_error(request):
        """
        Test endpoint for Sentry integration.
        Raises deliberate errors to verify Sentry is working.

        Only available when DEBUG=True.
        """
        error_type = request.GET.get("type", "division")

        if error_type == "division":
            # Test basic exception
            division_by_zero = 1 / 0
            return JsonResponse({"error": "This should never be reached"})
        elif error_type == "value":
            # Test value error
            raise ValueError("Test error from Storm Cloud - this is intentional!")
        elif error_type == "api_key":
            # Test sensitive data filtering
            fake_key = "test_api_key_1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_-"
            raise Exception(f"Error with API key: {fake_key}")
        else:
            return JsonResponse(
                {
                    "message": "Sentry test endpoint",
                    "usage": "Add ?type=division, ?type=value, or ?type=api_key to trigger errors",
                    "available_types": ["division", "value", "api_key"],
                }
            )

    urlpatterns += [
        path("debug/sentry-test/", sentry_test_error, name="sentry-test"),
    ]
