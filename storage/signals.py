"""Django signals for storage app file events."""

from django.dispatch import Signal

# Fired when any file action is performed
#
# Arguments:
#   sender: View class that triggered the signal
#   performed_by: User who performed the action
#   target_user: User whose files were affected
#   is_admin_action: bool - True if admin acted on another user's files
#   action: str - Action type (list, upload, download, delete, move, copy, edit, preview, etc.)
#   path: str - Primary path affected
#   success: bool - Whether the operation succeeded
#   request: Request object (for IP/user-agent extraction)
#
# Optional kwargs:
#   destination_path: str - For move/copy operations
#   paths_affected: list - For bulk operations
#   error_code: str - Error code if failed
#   error_message: str - Error message if failed
#   file_size: int - File size in bytes
#   content_type: str - MIME type
file_action_performed = Signal()
