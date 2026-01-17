"""Storage API views package.

Re-exports all views for backwards compatibility.
"""

from storage.api.bulk import BulkOperationView, BulkStatusView
from storage.api.utils import emit_user_file_action

from storage.api.admin import IndexRebuildView
from storage.api.audit import UserAuditLogPagination, UserAuditLogView
from storage.api.directories import (
    DirectoryCreateView,
    DirectoryListBaseView,
    DirectoryListRootView,
    DirectoryListView,
    DirectoryReorderView,
    DirectoryResetOrderView,
)
from storage.api.files import (
    FileContentView,
    FileCreateView,
    FileDeleteView,
    FileDetailView,
    FileDownloadView,
    FileUploadView,
)
from storage.api.shares import (
    PublicShareDownloadView,
    PublicShareInfoView,
    ShareLinkDetailView,
    ShareLinkListCreateView,
)
from storage.api.transfer import StorageTransferView

__all__ = [
    # Directory operations
    "DirectoryListBaseView",
    "DirectoryListRootView",
    "DirectoryListView",
    "DirectoryCreateView",
    "DirectoryReorderView",
    "DirectoryResetOrderView",
    # File operations
    "FileDetailView",
    "FileCreateView",
    "FileUploadView",
    "FileDownloadView",
    "FileContentView",
    "FileDeleteView",
    # Index rebuild
    "IndexRebuildView",
    # Share links
    "ShareLinkListCreateView",
    "ShareLinkDetailView",
    "PublicShareInfoView",
    "PublicShareDownloadView",
    # Bulk operations
    "BulkOperationView",
    "BulkStatusView",
    # Transfer
    "StorageTransferView",
    # Audit
    "UserAuditLogPagination",
    "UserAuditLogView",
    # Utilities
    "emit_user_file_action",
]
