"""URL configuration for Storm Cloud API v1."""

from django.urls import path
from django.http import JsonResponse

from accounts.api import (
    # Registration & Email Verification
    RegistrationView,
    EmailVerificationView,
    ResendVerificationView,
    # Session Auth
    LoginView,
    LogoutView,
    # API Keys
    APIKeyCreateView,
    APIKeyListView,
    APIKeyRevokeView,
    # Account Management
    AuthMeView,
    DeactivateAccountView,
    DeleteAccountView,
    # Admin
    AdminUserCreateView,
    AdminUserListView,
    AdminUserDetailView,
    AdminUserVerifyView,
    AdminUserDeactivateView,
    AdminUserActivateView,
    AdminAPIKeyListView,
    AdminAPIKeyRevokeView,
)
from storage.api import (
    DirectoryListView,
    DirectoryCreateView,
    FileUploadView,
    FileDetailView,
    FileDownloadView,
    FileDeleteView,
    IndexRebuildView,
)
from cms.api import (
    ManagedContentListView,
    ManagedContentAddView,
    ManagedContentRemoveView,
    ManagedContentRenderView,
)


# Health check views (simple, no authentication)
def health_ping(request):
    """Basic health check."""
    return JsonResponse({'status': 'ok'})


def health_status(request):
    """Detailed health status."""
    return JsonResponse({'status': 'ok', 'version': '0.1.0'})


urlpatterns = [
    # Health
    path('health/ping/', health_ping, name='health-ping'),
    path('health/status/', health_status, name='health-status'),

    # =========================================================================
    # Authentication & Authorization
    # =========================================================================

    # Registration & Email Verification
    path('auth/register/', RegistrationView.as_view(), name='auth-register'),
    path('auth/verify-email/', EmailVerificationView.as_view(), name='auth-verify-email'),
    path('auth/resend-verification/', ResendVerificationView.as_view(), name='auth-resend-verification'),

    # Session Authentication (for Swagger UI)
    path('auth/login/', LoginView.as_view(), name='auth-login'),
    path('auth/logout/', LogoutView.as_view(), name='auth-logout'),

    # Current User
    path('auth/me/', AuthMeView.as_view(), name='auth-me'),

    # API Key Management (tokens per spec) - List/Create combined
    path('auth/tokens/', APIKeyListView.as_view(), name='auth-tokens'),
    path('auth/tokens/<uuid:key_id>/revoke/', APIKeyRevokeView.as_view(), name='auth-tokens-revoke'),

    # Account Management
    path('auth/deactivate/', DeactivateAccountView.as_view(), name='auth-deactivate'),
    path('auth/delete/', DeleteAccountView.as_view(), name='auth-delete'),

    # =========================================================================
    # Admin Endpoints
    # =========================================================================

    # User Management (combined list/create endpoint)
    path('admin/users/', AdminUserListView.as_view(), name='admin-users'),
    path('admin/users/<int:user_id>/', AdminUserDetailView.as_view(), name='admin-users-detail'),
    path('admin/users/<int:user_id>/verify/', AdminUserVerifyView.as_view(), name='admin-users-verify'),
    path('admin/users/<int:user_id>/deactivate/', AdminUserDeactivateView.as_view(), name='admin-users-deactivate'),
    path('admin/users/<int:user_id>/activate/', AdminUserActivateView.as_view(), name='admin-users-activate'),

    # API Key Management (Admin)
    path('admin/keys/', AdminAPIKeyListView.as_view(), name='admin-keys-list'),
    path('admin/keys/<uuid:key_id>/revoke/', AdminAPIKeyRevokeView.as_view(), name='admin-keys-revoke'),

    # =========================================================================
    # Storage
    # =========================================================================

    # Directories (ls operations)
    path('dirs/', DirectoryListView.as_view(), name='dir-list-root'),
    path('dirs/<path:dir_path>/create/', DirectoryCreateView.as_view(), name='dir-create'),
    path('dirs/<path:dir_path>/', DirectoryListView.as_view(), name='dir-list'),


    # Files (file operations)
    path('files/<path:file_path>/upload/', FileUploadView.as_view(), name='file-upload'),
    path('files/<path:file_path>/download/', FileDownloadView.as_view(), name='file-download'),
    path('files/<path:file_path>/delete/', FileDeleteView.as_view(), name='file-delete'),

    path('files/<path:file_path>/', FileDetailView.as_view(), name='file-detail'),
    
    # Index management (admin)
    path('index/rebuild/', IndexRebuildView.as_view(), name='index-rebuild'),

    # CMS
    path('cms/', ManagedContentListView.as_view(), name='cms-list'),
    path('cms/add/', ManagedContentAddView.as_view(), name='cms-add'),
    path('cms/<uuid:content_id>/remove/', ManagedContentRemoveView.as_view(), name='cms-remove'),
    path('cms/<uuid:content_id>/render/', ManagedContentRenderView.as_view(), name='cms-render'),
    path('cms/render/', ManagedContentRenderView.as_view(), name='cms-render-bulk'),
]
