"""
Bulk Operations Service.

Enables batch file operations (delete, move, copy) on multiple files/folders
in a single request with partial success support.

Usage:
    service = BulkOperationService(account=request.user.account, backend=LocalStorageBackend())
    stats = service.execute(operation='delete', paths=['file1.txt', 'file2.txt'])
"""

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Union, Dict, Any
from django.db import transaction
from django.db.models import Sum

from core.storage.base import AbstractStorageBackend
from core.utils import normalize_path, PathValidationError
from storage.models import StoredFile

if TYPE_CHECKING:
    from accounts.models import Account


@dataclass
class BulkOperationResult:
    """Result for a single file operation in a bulk request."""

    path: str
    success: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    data: Optional[dict] = None


@dataclass
class BulkOperationStats:
    """Aggregate statistics for a bulk operation."""

    operation: str
    total: int
    succeeded: int
    failed: int
    results: List[BulkOperationResult] = field(default_factory=list)


class BulkOperationService:
    """
    Service for executing bulk file operations.

    Supports: delete, move, copy
    Each operation processes all paths independently - failures don't abort batch.
    """

    # Supported operations
    VALID_OPERATIONS = ["delete", "move", "copy"]

    # Maximum paths per request
    MAX_PATHS = 250

    # Async threshold (configurable via settings)
    ASYNC_THRESHOLD = 50

    def __init__(
        self,
        account: "Account",
        backend: AbstractStorageBackend,
        async_threshold: Optional[int] = None,
    ):
        """
        Initialize bulk operation service.

        Args:
            account: Account performing the operations
            backend: Storage backend instance
            async_threshold: Override default async threshold (for testing)
        """
        self.account = account
        self.backend = backend
        self.async_threshold = async_threshold or self.ASYNC_THRESHOLD
        # Use Account UUID for storage path prefix
        self.account_prefix = f"{account.id}"

    def execute(
        self,
        operation: str,
        paths: List[str],
        options: Optional[Dict] = None,
        force_sync: bool = False,
    ) -> Union[BulkOperationStats, Dict]:
        """
        Execute bulk operation on multiple paths.

        Args:
            operation: Operation to perform ('delete', 'move', 'copy')
            paths: List of file/directory paths
            options: Operation-specific options (e.g., destination for move/copy)
            force_sync: Force synchronous execution (for testing)

        Returns:
            BulkOperationStats if sync, or dict with task_id if async

        Raises:
            ValueError: If operation/paths validation fails
        """
        options = options or {}

        # Validate operation
        if operation not in self.VALID_OPERATIONS:
            raise ValueError(
                f"Invalid operation: {operation}. "
                f"Allowed: {', '.join(self.VALID_OPERATIONS)}"
            )

        # Validate paths
        if not paths:
            raise ValueError("Paths array cannot be empty")

        if not isinstance(paths, list):
            raise ValueError("Paths must be an array")

        if not all(isinstance(p, str) for p in paths):
            raise ValueError("All paths must be strings")

        if len(paths) > self.MAX_PATHS:
            raise ValueError(
                f"Maximum {self.MAX_PATHS} paths per request (received {len(paths)})"
            )

        # Validate operation-specific requirements
        if operation in ["move", "copy"]:
            if "destination" not in options:
                raise ValueError(f"Destination is required for {operation} operation")

        # Check if async execution is needed
        if len(paths) > self.async_threshold and not force_sync:
            return self._execute_async(operation, paths, options)

        # Execute synchronously
        return self._execute_sync(operation, paths, options)

    def _execute_sync(
        self, operation: str, paths: List[str], options: Dict
    ) -> BulkOperationStats:
        """Execute operation synchronously."""
        stats = BulkOperationStats(
            operation=operation, total=len(paths), succeeded=0, failed=0, results=[]
        )

        # Deduplicate paths while preserving order
        seen = set()
        unique_paths = []
        for path in paths:
            if path not in seen:
                seen.add(path)
                unique_paths.append(path)

        # Use bulk method for delete to avoid N+1 queries
        if operation == "delete":
            results = self._execute_bulk_delete(unique_paths)
            for result in results:
                stats.results.append(result)
                if result.success:
                    stats.succeeded += 1
                else:
                    stats.failed += 1
            return stats

        # Execute operation for each path (move/copy still use per-path logic)
        for path in unique_paths:
            result: BulkOperationResult
            if operation == "move":
                result = self._execute_move(path, options["destination"])
            elif operation == "copy":
                result = self._execute_copy(path, options["destination"])
            else:
                # This should never happen due to validation, but satisfy type checker
                result = BulkOperationResult(
                    path=path,
                    success=False,
                    error_code="INVALID_OPERATION",
                    error_message=f"Unknown operation: {operation}",
                )

            stats.results.append(result)
            if result.success:
                stats.succeeded += 1
            else:
                stats.failed += 1

        return stats

    def _execute_async(self, operation: str, paths: List[str], options: Dict) -> Dict:
        """Queue operation for async execution."""
        from storage.tasks import bulk_operation_task, TASKS_AVAILABLE

        # If async tasks not available, fall back to sync execution
        if not TASKS_AVAILABLE:
            stats = self._execute_sync(operation, paths, options)
            # Return sync result in async format for API compatibility
            return {
                "async": False,
                "immediate": True,
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

        # Enqueue task
        result = bulk_operation_task.enqueue(
            operation=operation,
            paths=paths,
            options=options,
            account_id=str(self.account.id),
        )

        return {
            "async": True,
            "task_id": str(result.id),
            "total": len(paths),
            "status_url": f"/api/v1/bulk/status/{result.id}/",
        }

    def _execute_bulk_delete(self, paths: List[str]) -> List[BulkOperationResult]:
        """
        Delete multiple files efficiently with batched DB operations.

        Implements "filesystem wins" - delete from filesystem first,
        then bulk remove DB records. Uses single SELECT and single DELETE
        to avoid N+1 query patterns.

        Args:
            paths: List of file paths to delete

        Returns:
            List of BulkOperationResult for each path
        """
        results: List[BulkOperationResult] = []

        # 1. Normalize and validate all paths upfront
        path_map: dict[str, str] = {}  # normalized_path -> original_path
        for path in paths:
            try:
                normalized = normalize_path(path)
                path_map[normalized] = path
            except PathValidationError as e:
                results.append(
                    BulkOperationResult(
                        path=path,
                        success=False,
                        error_code="INVALID_PATH",
                        error_message=str(e),
                    )
                )

        if not path_map:
            return results

        # 2. Fetch ALL StoredFile records in ONE query
        db_files: dict[str, StoredFile] = {
            f.path: f
            for f in StoredFile.objects.filter(
                owner=self.account, path__in=path_map.keys()
            )
        }

        # 3. Process filesystem deletions, track successful DB records
        successful_file_ids: List[int] = []

        for normalized_path, original_path in path_map.items():
            full_path = f"{self.account_prefix}/{normalized_path}"
            db_file = db_files.get(normalized_path)

            # Check existence - need either DB record or filesystem presence
            if not db_file and not self.backend.exists(full_path):
                results.append(
                    BulkOperationResult(
                        path=original_path,
                        success=False,
                        error_code="NOT_FOUND",
                        error_message=f"File not found: {original_path}",
                    )
                )
                continue

            # Delete from filesystem
            try:
                try:
                    file_info = self.backend.info(full_path)

                    if file_info.is_directory:
                        # Recursive delete for directories
                        resolved_path = self.backend._resolve_path(full_path)  # type: ignore[attr-defined]
                        if resolved_path.exists():
                            shutil.rmtree(resolved_path)
                    else:
                        # Regular file delete
                        self.backend.delete(full_path)
                except FileNotFoundError:
                    # Already deleted or doesn't exist - that's OK
                    pass

                # Track successful deletion for bulk DB cleanup
                if db_file:
                    successful_file_ids.append(db_file.id)

                results.append(BulkOperationResult(path=original_path, success=True))

            except Exception as e:
                results.append(
                    BulkOperationResult(
                        path=original_path,
                        success=False,
                        error_code="DELETE_FAILED",
                        error_message=f"Filesystem error: {str(e)}",
                    )
                )

        # 4. Bulk delete ALL successful DB records in ONE operation
        # Django handles CASCADE automatically (ShareLinks, ManagedContent)
        if successful_file_ids:
            StoredFile.objects.filter(id__in=successful_file_ids).delete()

        return results

    def _execute_delete(self, path: str) -> BulkOperationResult:
        """
        Delete a single file or directory.

        Implements "filesystem wins" - delete from filesystem first,
        then remove DB record.
        """
        try:
            # Normalize and validate path
            try:
                normalized_path = normalize_path(path)
            except PathValidationError as e:
                return BulkOperationResult(
                    path=path,
                    success=False,
                    error_code="INVALID_PATH",
                    error_message=str(e),
                )

            full_path = f"{self.account_prefix}/{normalized_path}"

            # Check if file exists and user owns it
            try:
                db_file = StoredFile.objects.get(
                    owner=self.account, path=normalized_path
                )
            except StoredFile.DoesNotExist:
                # Check if it exists on filesystem
                if not self.backend.exists(full_path):
                    return BulkOperationResult(
                        path=path,
                        success=False,
                        error_code="NOT_FOUND",
                        error_message=f"File not found: {path}",
                    )
                # Exists on filesystem but not in DB - proceed with filesystem deletion
                db_file = None

            # Delete from filesystem (handles both files and directories)
            try:
                file_info = self.backend.info(full_path)

                if file_info.is_directory:
                    # Recursive delete for directories
                    # LocalStorageBackend has _resolve_path but it's not in abstract interface
                    resolved_path = self.backend._resolve_path(full_path)  # type: ignore[attr-defined]
                    if resolved_path.exists():
                        shutil.rmtree(resolved_path)
                else:
                    # Regular file delete
                    self.backend.delete(full_path)

            except FileNotFoundError:
                # Already deleted or doesn't exist
                pass
            except Exception as e:
                return BulkOperationResult(
                    path=path,
                    success=False,
                    error_code="DELETE_FAILED",
                    error_message=f"Filesystem error: {str(e)}",
                )

            # Delete from database (CASCADE handles ShareLinks)
            if db_file:
                db_file.delete()

            return BulkOperationResult(path=path, success=True)

        except Exception as e:
            return BulkOperationResult(
                path=path,
                success=False,
                error_code="DELETE_FAILED",
                error_message=str(e),
            )

    def _execute_move(self, path: str, destination: str) -> BulkOperationResult:
        """
        Move a single file or directory to new location.

        Implements "filesystem wins" - move on filesystem first,
        then update DB records.
        """
        try:
            # Normalize and validate paths
            try:
                normalized_path = normalize_path(path)
                normalized_dest = normalize_path(destination) if destination else ""
            except PathValidationError as e:
                return BulkOperationResult(
                    path=path,
                    success=False,
                    error_code="INVALID_PATH",
                    error_message=str(e),
                )

            source_full = f"{self.account_prefix}/{normalized_path}"
            dest_full = (
                f"{self.account_prefix}/{normalized_dest}"
                if normalized_dest
                else self.account_prefix
            )

            # Check if source exists and user owns it
            try:
                db_file = StoredFile.objects.get(
                    owner=self.account, path=normalized_path
                )
            except StoredFile.DoesNotExist:
                return BulkOperationResult(
                    path=path,
                    success=False,
                    error_code="NOT_FOUND",
                    error_message=f"File not found: {path}",
                )

            # Check if destination directory exists
            if not self.backend.exists(dest_full):
                return BulkOperationResult(
                    path=path,
                    success=False,
                    error_code="DESTINATION_NOT_FOUND",
                    error_message=f"Destination directory not found: {destination}",
                )

            # Move on filesystem
            try:
                new_file_info = self.backend.move(source_full, dest_full)
            except FileNotFoundError:
                return BulkOperationResult(
                    path=path,
                    success=False,
                    error_code="NOT_FOUND",
                    error_message=f"Source not found: {path}",
                )
            except FileExistsError:
                return BulkOperationResult(
                    path=path,
                    success=False,
                    error_code="ALREADY_EXISTS",
                    error_message=f"File with same name already exists at destination: {destination}",
                )
            except Exception as e:
                return BulkOperationResult(
                    path=path,
                    success=False,
                    error_code="MOVE_FAILED",
                    error_message=f"Filesystem error: {str(e)}",
                )

            # Update database record
            # Calculate new path (relative to user root)
            new_relative_path = new_file_info.path.replace(
                f"{self.account_prefix}/", ""
            )
            new_parent_path = (
                str(Path(new_relative_path).parent) if "/" in new_relative_path else ""
            )
            if new_parent_path == ".":
                new_parent_path = ""

            with transaction.atomic():
                db_file.path = new_relative_path
                db_file.parent_path = new_parent_path
                db_file.save()

            return BulkOperationResult(
                path=path, success=True, data={"new_path": new_relative_path}
            )

        except Exception as e:
            return BulkOperationResult(
                path=path, success=False, error_code="MOVE_FAILED", error_message=str(e)
            )

    def _execute_copy(self, path: str, destination: str) -> BulkOperationResult:
        """
        Copy a single file or directory to new location.

        Implements "filesystem wins" - copy on filesystem first,
        then create DB records. Handles name collisions with " (copy)" suffix.
        """
        try:
            # Normalize and validate paths
            try:
                normalized_path = normalize_path(path)
                normalized_dest = normalize_path(destination) if destination else ""
            except PathValidationError as e:
                return BulkOperationResult(
                    path=path,
                    success=False,
                    error_code="INVALID_PATH",
                    error_message=str(e),
                )

            source_full = f"{self.account_prefix}/{normalized_path}"
            dest_full = (
                f"{self.account_prefix}/{normalized_dest}"
                if normalized_dest
                else self.account_prefix
            )

            # Check if source exists and user owns it
            try:
                db_file = StoredFile.objects.get(
                    owner=self.account, path=normalized_path
                )
            except StoredFile.DoesNotExist:
                return BulkOperationResult(
                    path=path,
                    success=False,
                    error_code="NOT_FOUND",
                    error_message=f"File not found: {path}",
                )

            # Check if destination directory exists
            if not self.backend.exists(dest_full):
                return BulkOperationResult(
                    path=path,
                    success=False,
                    error_code="DESTINATION_NOT_FOUND",
                    error_message=f"Destination directory not found: {destination}",
                )

            # Check quota before copying
            if db_file.size > 0:
                # Get account's current storage usage
                storage_used_bytes = (
                    StoredFile.objects.filter(owner=self.account).aggregate(
                        total=Sum("size")
                    )["total"]
                    or 0
                )

                # Check if quota is set and would be exceeded
                if self.account.storage_quota_bytes > 0:
                    if (
                        storage_used_bytes + db_file.size
                        > self.account.storage_quota_bytes
                    ):
                        quota_mb = self.account.storage_quota_bytes / (1024 * 1024)
                        used_mb = storage_used_bytes / (1024 * 1024)
                        return BulkOperationResult(
                            path=path,
                            success=False,
                            error_code="QUOTA_EXCEEDED",
                            error_message=f"Storage quota exceeded (using {used_mb:.1f}MB of {quota_mb:.1f}MB)",
                        )

            # Copy on filesystem (handles name collisions automatically)
            try:
                new_file_info = self.backend.copy(source_full, dest_full)
            except FileNotFoundError as e:
                # Determine if source or destination is missing
                if not self.backend.exists(source_full):
                    return BulkOperationResult(
                        path=path,
                        success=False,
                        error_code="NOT_FOUND",
                        error_message=f"Source not found: {path}",
                    )
                else:
                    return BulkOperationResult(
                        path=path,
                        success=False,
                        error_code="DESTINATION_NOT_FOUND",
                        error_message=f"Destination not found: {destination}",
                    )
            except Exception as e:
                return BulkOperationResult(
                    path=path,
                    success=False,
                    error_code="COPY_FAILED",
                    error_message=f"Filesystem error: {str(e)}",
                )

            # Create new database record for the copy
            new_relative_path = new_file_info.path.replace(
                f"{self.account_prefix}/", ""
            )
            new_parent_path = (
                str(Path(new_relative_path).parent) if "/" in new_relative_path else ""
            )
            if new_parent_path == ".":
                new_parent_path = ""

            with transaction.atomic():
                # Create new StoredFile record (don't copy ShareLinks per spec)
                StoredFile.objects.create(
                    owner=self.account,
                    path=new_relative_path,
                    name=new_file_info.name,
                    size=new_file_info.size,
                    content_type=new_file_info.content_type or "",
                    is_directory=new_file_info.is_directory,
                    parent_path=new_parent_path,
                    encryption_method=db_file.encryption_method,
                    sort_position=None,  # New files use alphabetical sort
                )

            return BulkOperationResult(
                path=path, success=True, data={"new_path": new_relative_path}
            )

        except Exception as e:
            return BulkOperationResult(
                path=path, success=False, error_code="COPY_FAILED", error_message=str(e)
            )
