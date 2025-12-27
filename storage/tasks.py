"""
Background tasks for storage app.

Uses Django 6.0 Tasks framework for async operations.
"""

import logging
from typing import Optional, List, Dict
from django.contrib.auth import get_user_model

try:
    from django.tasks import task  # Django 6.0+

    TASKS_AVAILABLE = True
except ImportError:
    # Fallback for Django <6.0 - create a no-op decorator
    TASKS_AVAILABLE = False

    def task(*args, **kwargs):
        def decorator(func):
            return func

        if args and callable(args[0]):
            return args[0]
        return decorator


from core.services.index_sync import IndexSyncService
from core.services.bulk import BulkOperationService, BulkOperationStats
from core.storage.local import LocalStorageBackend

logger = logging.getLogger(__name__)
User = get_user_model()


@task(
    takes_context=True,
    # Note: ImmediateBackend doesn't support priority/queue_name
    # These will be used when production backend is configured
)
def rebuild_storage_index(
    context,
    mode: str = "audit",
    user_id: Optional[int] = None,
    dry_run: bool = False,
    force: bool = False,
):
    """
    Rebuild storage index from filesystem.

    Implements ADR 000 risk mitigation: "Index rebuild, filesystem wins"

    Args:
        context: TaskContext (automatic from Django Tasks)
        mode: 'audit', 'sync', 'clean', or 'full'
        user_id: Specific user ID or None for all users
        dry_run: Preview changes without applying
        force: Required for 'clean' and 'full' modes

    Returns:
        dict: IndexSyncStats as dictionary
    """
    logger.info(
        f"Index rebuild task started: mode={mode}, user_id={user_id}, "
        f"dry_run={dry_run}, force={force}, attempt={context.attempt}"
    )

    try:
        service = IndexSyncService(user_id=user_id)
        stats = service.sync(mode=mode, dry_run=dry_run, force=force)

        # Convert dataclass to dict for JSON serialization
        result = {
            "status": "success",
            "mode": mode,
            "dry_run": dry_run,
            "users_scanned": stats.users_scanned,
            "files_on_disk": stats.files_on_disk,
            "files_in_db": stats.files_in_db,
            "missing_in_db": stats.missing_in_db,
            "orphaned_in_db": stats.orphaned_in_db,
            "records_created": stats.records_created,
            "records_deleted": stats.records_deleted,
            "records_skipped": stats.records_skipped,
            "errors": stats.errors,
        }

        logger.info(
            f"Index rebuild completed: "
            f"created={stats.records_created}, "
            f"deleted={stats.records_deleted}, "
            f"errors={len(stats.errors)}"
        )

        return result

    except Exception as e:
        logger.error(f"Index rebuild failed: {e}", exc_info=True)
        raise  # Django Tasks will capture traceback


@task(takes_context=True)
def bulk_operation_task(
    context,
    operation: str,
    paths: List[str],
    options: Optional[Dict],
    user_id: int,
):
    """
    Execute bulk file operation asynchronously.

    Args:
        context: TaskContext (automatic from Django Tasks)
        operation: Operation to perform ('delete', 'move', 'copy')
        paths: List of file/directory paths
        options: Operation-specific options (e.g., destination)
        user_id: ID of user performing operations

    Returns:
        dict: BulkOperationStats as dictionary
    """
    logger.info(
        f"Bulk operation task started: operation={operation}, "
        f"paths_count={len(paths)}, user_id={user_id}, attempt={context.attempt}"
    )

    try:
        # Get user
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            error_msg = f"User not found: {user_id}"
            logger.error(error_msg)
            return {"status": "error", "error": error_msg}

        # Create service and execute
        backend = LocalStorageBackend()
        service = BulkOperationService(user=user, backend=backend)

        # force_sync=True ensures we don't recursively queue tasks
        stats = service.execute(
            operation=operation, paths=paths, options=options, force_sync=True
        )

        # force_sync=True guarantees BulkOperationStats return type
        assert isinstance(stats, BulkOperationStats)

        # Convert BulkOperationStats to dict for JSON serialization
        result = {
            "status": "complete",
            "operation": stats.operation,
            "total": stats.total,
            "succeeded": stats.succeeded,
            "failed": stats.failed,
            "results": [
                {
                    "path": r.path,
                    "success": r.success,
                    "error_code": r.error_code,
                    "error_message": r.error_message,
                    "data": r.data,
                }
                for r in stats.results
            ],
        }

        logger.info(
            f"Bulk operation completed: operation={operation}, "
            f"succeeded={stats.succeeded}, failed={stats.failed}"
        )

        return result

    except Exception as e:
        logger.error(f"Bulk operation failed: {e}", exc_info=True)
        raise  # Django Tasks will capture traceback
