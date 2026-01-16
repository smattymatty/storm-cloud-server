"""URL configuration for Storm Cloud API v1."""

import time

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path

from accounts.api import (
    AdminAPIKeyListView,
    AdminAPIKeyRevokeView,
    AdminUserActivateView,
    AdminUserAPIKeyCreateView,
    # Admin
    AdminUserCreateView,
    AdminUserDeactivateView,
    AdminUserDetailView,
    AdminUserListView,
    AdminUserPasswordResetView,
    AdminUserQuotaUpdateView,
    AdminUserPermissionsUpdateView,
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
    # Webhook Configuration
    WebhookConfigView,
    WebhookRegenerateSecretView,
    WebhookTestView,
    # Admin Webhook Management
    AdminUserKeyWebhookView,
    AdminUserKeyWebhookRegenerateView,
    AdminUserKeyWebhookTestView,
    # Admin Organization Management
    AdminOrganizationListView,
    AdminOrganizationDetailView,
    AdminOrganizationMembersView,
    # User Per-Key Webhook
    UserKeyWebhookView,
)
from accounts.enrollment_api import (
    EnrollmentValidateView,
    EnrollmentEnrollView,
    EnrollmentStatusView,
    EnrollmentResendView,
    EnrollmentInviteCreateView,
    EmailStatusView,
)
from accounts.admin_invite_api import (
    AdminInviteListView,
    AdminInviteRevokeView,
    AdminInviteResendView,
    AdminInviteBulkRevokeView,
)
from accounts.platform_api import (
    PlatformEnrollView,
    PlatformInviteCreateView,
    PlatformInviteDetailView,
    PlatformInviteListView,
    PlatformInviteValidateView,
    PlatformSetupOrgView,
)
from storage.api import (
    BulkOperationView,
    BulkStatusView,
    DirectoryCreateView,
    DirectoryListRootView,
    DirectoryListView,
    DirectoryReorderView,
    DirectoryResetOrderView,
    FileContentView,
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
    UserAuditLogView,
)
from storage.admin_api import (
    AdminBulkOperationView,
    AdminDirectoryCreateView,
    AdminDirectoryListRootView,
    AdminDirectoryListView,
    AdminFileAuditLogListView,
    AdminFileContentView,
    AdminFileCreateView,
    AdminFileDeleteView,
    AdminFileDetailView,
    AdminFileDownloadView,
    AdminFileUploadView,
)
from storage.search_api import AdminSearchFilesView, SearchFilesView
from storage.shared_api import (
    SharedDirectoryCreateView,
    SharedDirectoryListRootView,
    SharedDirectoryListView,
    SharedFileContentView,
    SharedFileDeleteView,
    SharedFileDetailView,
    SharedFileDownloadView,
    SharedFileUploadView,
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
        from core.storage import get_storage_backend  # type: ignore[attr-defined]

        backend = get_storage_backend()  # type: ignore[operator]
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
    # Enrollment (invite-based registration)
    path(
        "enrollment/validate/",
        EnrollmentValidateView.as_view(),
        name="enrollment-validate",
    ),
    path(
        "enrollment/enroll/",
        EnrollmentEnrollView.as_view(),
        name="enrollment-enroll",
    ),
    path(
        "enrollment/status/<uuid:enrollment_id>/",
        EnrollmentStatusView.as_view(),
        name="enrollment-status",
    ),
    path(
        "enrollment/resend/<uuid:enrollment_id>/",
        EnrollmentResendView.as_view(),
        name="enrollment-resend",
    ),
    path(
        "enrollment/invite/create/",
        EnrollmentInviteCreateView.as_view(),
        name="enrollment-invite-create",
    ),
    path(
        "enrollment/email-status/",
        EmailStatusView.as_view(),
        name="enrollment-email-status",
    ),
    # Platform Invites (client-first enrollment)
    path(
        "platform/invite/create/",
        PlatformInviteCreateView.as_view(),
        name="platform-invite-create",
    ),
    path(
        "platform/invite/validate/",
        PlatformInviteValidateView.as_view(),
        name="platform-invite-validate",
    ),
    path(
        "platform/invites/",
        PlatformInviteListView.as_view(),
        name="platform-invite-list",
    ),
    path(
        "platform/invites/<uuid:invite_id>/",
        PlatformInviteDetailView.as_view(),
        name="platform-invite-detail",
    ),
    path(
        "platform/enroll/",
        PlatformEnrollView.as_view(),
        name="platform-enroll",
    ),
    path(
        "platform/setup-org/",
        PlatformSetupOrgView.as_view(),
        name="platform-setup-org",
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
    path(
        "auth/tokens/<uuid:key_id>/webhook/",
        UserKeyWebhookView.as_view(),
        name="user-key-webhook",
    ),
    # Account Management
    path("auth/deactivate/", DeactivateAccountView.as_view(), name="auth-deactivate"),
    path("auth/delete/", DeleteAccountView.as_view(), name="auth-delete"),
    # Webhook Configuration
    path("account/webhook/", WebhookConfigView.as_view(), name="webhook-config"),
    path(
        "account/webhook/regenerate-secret/",
        WebhookRegenerateSecretView.as_view(),
        name="webhook-regenerate",
    ),
    path("account/webhook/test/", WebhookTestView.as_view(), name="webhook-test"),
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
    path(
        "admin/users/<int:user_id>/quota/",
        AdminUserQuotaUpdateView.as_view(),
        name="admin-users-quota",
    ),
    path(
        "admin/users/<int:user_id>/permissions/",
        AdminUserPermissionsUpdateView.as_view(),
        name="admin-users-permissions",
    ),
    path(
        "admin/users/<int:user_id>/keys/",
        AdminUserAPIKeyCreateView.as_view(),
        name="admin-users-keys-create",
    ),
    # API Key Management (Admin)
    path("admin/keys/", AdminAPIKeyListView.as_view(), name="admin-keys-list"),
    path(
        "admin/keys/<uuid:key_id>/revoke/",
        AdminAPIKeyRevokeView.as_view(),
        name="admin-keys-revoke",
    ),
    # Organization Management (Admin)
    path(
        "admin/organizations/",
        AdminOrganizationListView.as_view(),
        name="admin-organizations",
    ),
    path(
        "admin/organizations/<uuid:org_id>/",
        AdminOrganizationDetailView.as_view(),
        name="admin-organization-detail",
    ),
    path(
        "admin/organizations/<uuid:org_id>/members/",
        AdminOrganizationMembersView.as_view(),
        name="admin-organization-members",
    ),
    # Admin Webhook Management (per user's key)
    path(
        "admin/users/<int:user_id>/keys/<uuid:key_id>/webhook/",
        AdminUserKeyWebhookView.as_view(),
        name="admin-user-key-webhook",
    ),
    path(
        "admin/users/<int:user_id>/keys/<uuid:key_id>/webhook/regenerate-secret/",
        AdminUserKeyWebhookRegenerateView.as_view(),
        name="admin-user-key-webhook-regenerate",
    ),
    path(
        "admin/users/<int:user_id>/keys/<uuid:key_id>/webhook/test/",
        AdminUserKeyWebhookTestView.as_view(),
        name="admin-user-key-webhook-test",
    ),
    # -------------------------------------------------------------------------
    # Admin File Operations (act on user's files)
    # -------------------------------------------------------------------------
    # Audit Log
    path(
        "admin/audit/files/",
        AdminFileAuditLogListView.as_view(),
        name="admin-audit-files",
    ),
    # User's directories
    path(
        "admin/users/<int:user_id>/dirs/",
        AdminDirectoryListRootView.as_view(),
        name="admin-user-dir-list-root",
    ),
    path(
        "admin/users/<int:user_id>/dirs/<path:dir_path>/create/",
        AdminDirectoryCreateView.as_view(),
        name="admin-user-dir-create",
    ),
    path(
        "admin/users/<int:user_id>/dirs/<path:dir_path>/",
        AdminDirectoryListView.as_view(),
        name="admin-user-dir-list",
    ),
    # User's files
    path(
        "admin/users/<int:user_id>/files/<path:file_path>/upload/",
        AdminFileUploadView.as_view(),
        name="admin-user-file-upload",
    ),
    path(
        "admin/users/<int:user_id>/files/<path:file_path>/create/",
        AdminFileCreateView.as_view(),
        name="admin-user-file-create",
    ),
    path(
        "admin/users/<int:user_id>/files/<path:file_path>/download/",
        AdminFileDownloadView.as_view(),
        name="admin-user-file-download",
    ),
    path(
        "admin/users/<int:user_id>/files/<path:file_path>/delete/",
        AdminFileDeleteView.as_view(),
        name="admin-user-file-delete",
    ),
    path(
        "admin/users/<int:user_id>/files/<path:file_path>/content/",
        AdminFileContentView.as_view(),
        name="admin-user-file-content",
    ),
    path(
        "admin/users/<int:user_id>/files/<path:file_path>/",
        AdminFileDetailView.as_view(),
        name="admin-user-file-detail",
    ),
    # User's bulk operations
    path(
        "admin/users/<int:user_id>/bulk/",
        AdminBulkOperationView.as_view(),
        name="admin-user-bulk-operation",
    ),
    # User's file search
    path(
        "admin/users/<int:user_id>/search/files/",
        AdminSearchFilesView.as_view(),
        name="admin-user-search-files",
    ),
    # -------------------------------------------------------------------------
    # Admin CMS Operations (act on user's CMS data)
    # -------------------------------------------------------------------------
    path(
        "admin/users/<int:user_id>/cms/",
        include("cms.admin_urls"),
    ),
    # -------------------------------------------------------------------------
    # Admin: Invite Management
    # -------------------------------------------------------------------------
    path("admin/invites/", AdminInviteListView.as_view(), name="admin-invites"),
    path(
        "admin/invites/<uuid:invite_id>/revoke/",
        AdminInviteRevokeView.as_view(),
        name="admin-invite-revoke",
    ),
    path(
        "admin/invites/<uuid:invite_id>/resend/",
        AdminInviteResendView.as_view(),
        name="admin-invite-resend",
    ),
    path(
        "admin/invites/bulk-revoke/",
        AdminInviteBulkRevokeView.as_view(),
        name="admin-invites-bulk-revoke",
    ),
    # =========================================================================
    # Storage
    # =========================================================================
    # Recursive file search
    path("search/files/", SearchFilesView.as_view(), name="search-files"),
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
    path(
        "files/<path:file_path>/content/",
        FileContentView.as_view(),
        name="file-content",
    ),
    path("files/<path:file_path>/", FileDetailView.as_view(), name="file-detail"),
    # Bulk operations
    path("bulk/", BulkOperationView.as_view(), name="bulk-operation"),
    path("bulk/status/<uuid:task_id>/", BulkStatusView.as_view(), name="bulk-status"),
    # Index management (admin)
    path("index/rebuild/", IndexRebuildView.as_view(), name="index-rebuild"),
    # User audit log
    path("audit/me/", UserAuditLogView.as_view(), name="audit-me"),
    # CMS (page-file mappings)
    path("cms/", include("cms.urls")),
    # =========================================================================
    # Shared Storage (Organization)
    # =========================================================================
    # Shared directories
    path("shared/", SharedDirectoryListRootView.as_view(), name="shared-dir-list-root"),
    path(
        "shared/dirs/<path:dir_path>/create/",
        SharedDirectoryCreateView.as_view(),
        name="shared-dir-create",
    ),
    path(
        "shared/dirs/<path:dir_path>/",
        SharedDirectoryListView.as_view(),
        name="shared-dir-list",
    ),
    # Shared files
    path(
        "shared/files/<path:file_path>/upload/",
        SharedFileUploadView.as_view(),
        name="shared-file-upload",
    ),
    path(
        "shared/files/<path:file_path>/download/",
        SharedFileDownloadView.as_view(),
        name="shared-file-download",
    ),
    path(
        "shared/files/<path:file_path>/delete/",
        SharedFileDeleteView.as_view(),
        name="shared-file-delete",
    ),
    path(
        "shared/files/<path:file_path>/content/",
        SharedFileContentView.as_view(),
        name="shared-file-content",
    ),
    path(
        "shared/files/<path:file_path>/",
        SharedFileDetailView.as_view(),
        name="shared-file-detail",
    ),
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
# Development Debug Endpoints
# =============================================================================
# Additional debug endpoints can be added here when DEBUG=True
