"""
Filesystem-Database Index Synchronization Service.

Implements ADR 000: "Filesystem wins" - filesystem is source of truth,
database is rebuildable index.

Usage:
    service = IndexSyncService(user_id=1)
    stats = service.sync(mode='audit', dry_run=True)
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List
from django.contrib.auth import get_user_model
from core.storage.base import AbstractStorageBackend
from core.storage.local import LocalStorageBackend
from storage.models import StoredFile

logger = logging.getLogger(__name__)


@dataclass
class IndexSyncStats:
    """Statistics from index sync operation."""
    users_scanned: int = 0
    files_on_disk: int = 0
    files_in_db: int = 0
    missing_in_db: int = 0
    orphaned_in_db: int = 0
    records_created: int = 0
    records_deleted: int = 0
    records_skipped: int = 0
    errors: List[str] = field(default_factory=list)


class IndexSyncService:
    """
    Service for synchronizing filesystem and database index.
    
    Modes:
        - audit: Report discrepancies only, no changes
        - sync: Add missing DB records for filesystem files
        - clean: Delete orphaned DB records (requires force=True)
        - full: sync + clean (requires force=True)
    """
    
    def __init__(
        self,
        backend: Optional[AbstractStorageBackend] = None,
        user_id: Optional[int] = None
    ):
        self.backend = backend or LocalStorageBackend()
        self.user_id = user_id
        
    def sync(
        self,
        mode: str = 'audit',
        dry_run: bool = False,
        force: bool = False,
    ) -> IndexSyncStats:
        """
        Synchronize filesystem and database index.
        
        Args:
            mode: 'audit', 'sync', 'clean', or 'full'
            dry_run: Preview changes without applying
            force: Required for 'clean' and 'full' modes
            
        Returns:
            IndexSyncStats with operation results
        """
        # Validate mode
        if mode not in ['audit', 'sync', 'clean', 'full']:
            raise ValueError(f"Invalid mode: {mode}")
            
        # Require force for destructive operations
        if mode in ['clean', 'full'] and not force:
            raise ValueError(f"Mode '{mode}' requires force=True")
        
        stats = IndexSyncStats()
        
        # Get users to scan
        User = get_user_model()
        if self.user_id:
            users = User.objects.filter(id=self.user_id)
        else:
            users = User.objects.all()
        
        stats.users_scanned = users.count()
        
        for user in users:
            user_stats = self._sync_user(user, mode, dry_run)
            # Aggregate stats
            stats.files_on_disk += user_stats.files_on_disk
            stats.files_in_db += user_stats.files_in_db
            stats.missing_in_db += user_stats.missing_in_db
            stats.orphaned_in_db += user_stats.orphaned_in_db
            stats.records_created += user_stats.records_created
            stats.records_deleted += user_stats.records_deleted
            stats.records_skipped += user_stats.records_skipped
            stats.errors.extend(user_stats.errors)
        
        return stats
    
    def _sync_user(
        self,
        user,
        mode: str,
        dry_run: bool
    ) -> IndexSyncStats:
        """
        Sync a single user's files between filesystem and database.
        
        Clean mode implements "filesystem wins" absolutely:
        - Orphaned DB records are deleted
        - Django CASCADE automatically deletes related ShareLinks
        - This is intentional: ShareLinks to non-existent files are invalid
        
        Args:
            user: Django User object to sync
            mode: 'audit', 'sync', 'clean', or 'full'
            dry_run: Preview changes without applying
            
        Returns:
            IndexSyncStats with operation results
        """
        stats = IndexSyncStats()
        user_prefix = f"{user.id}"
        
        # Scan filesystem
        fs_files = self._scan_filesystem(user_prefix)
        stats.files_on_disk = len(fs_files)
        
        # Get DB records
        db_files = {
            f.path: f for f in StoredFile.objects.filter(owner=user)
        }
        stats.files_in_db = len(db_files)
        
        # Find discrepancies
        fs_paths = set(fs_files.keys())
        db_paths = set(db_files.keys())
        
        missing_in_db = fs_paths - db_paths
        orphaned_in_db = db_paths - fs_paths
        in_both = fs_paths & db_paths
        
        stats.missing_in_db = len(missing_in_db)
        stats.orphaned_in_db = len(orphaned_in_db)
        
        # Sync missing files (mode: sync or full)
        if mode in ['sync', 'full']:
            for path in missing_in_db:
                file_info = fs_files[path]
                if not dry_run:
                    try:
                        obj, created = self._create_db_record(user, path, file_info)
                        if created:
                            stats.records_created += 1
                    except Exception as e:
                        stats.errors.append(f"Error creating {path}: {e}")
                else:
                    stats.records_created += 1
            
            # Also update files that exist in both but may have stale metadata
            # This implements "filesystem wins" policy
            for path in in_both:
                file_info = fs_files[path]
                db_file = db_files[path]
                
                # Check if metadata differs (filesystem wins)
                needs_update = (
                    db_file.size != file_info['size'] or
                    db_file.is_directory != file_info['is_directory'] or
                    db_file.content_type != file_info['content_type']
                )
                
                if needs_update:
                    if not dry_run:
                        try:
                            obj, created = self._create_db_record(user, path, file_info)
                            if created:
                                stats.records_created += 1
                        except Exception as e:
                            stats.errors.append(f"Error updating {path}: {e}")
                    else:
                        stats.records_created += 1
        
        # Clean orphaned records (mode: clean or full)
        # Note: Django CASCADE will automatically delete related ShareLinks
        # This implements "filesystem wins" - if file is gone, everything goes
        if mode in ['clean', 'full']:
            for path in orphaned_in_db:
                db_file = db_files[path]
                
                if not dry_run:
                    try:
                        # Log CASCADE deletions for transparency
                        sharelink_count = 0
                        if hasattr(db_file, 'share_links'):
                            sharelink_count = db_file.share_links.count()
                            if sharelink_count > 0:
                                logger.info(
                                    f"Deleting '{path}' (will CASCADE delete "
                                    f"{sharelink_count} ShareLink(s))"
                                )
                        
                        # Delete will CASCADE to related ShareLinks automatically
                        db_file.delete()
                        stats.records_deleted += 1
                    except Exception as e:
                        stats.errors.append(f"Error deleting {path}: {e}")
                else:
                    stats.records_deleted += 1
        
        return stats
    
    def _scan_filesystem(self, user_prefix: str) -> Dict[str, dict]:
        """
        Scan filesystem for user's files.
        
        Returns:
            Dict mapping relative_path -> file_info
        """
        files = {}
        
        try:
            for file_info in self._list_recursive(user_prefix):
                relative_path = file_info.path.replace(f"{user_prefix}/", "")
                files[relative_path] = {
                    'name': file_info.name,
                    'size': file_info.size,
                    'is_directory': file_info.is_directory,
                    'content_type': file_info.content_type or '',
                    'modified_at': file_info.modified_at,
                }
        except FileNotFoundError:
            # User directory doesn't exist yet
            pass
        
        return files
    
    def _list_recursive(self, path: str):
        """Recursively list all files in a directory."""
        for item in self.backend.list(path):
            yield item
            if item.is_directory:
                yield from self._list_recursive(item.path)
    
    def _create_db_record(self, user, path: str, file_info: dict):
        """
        Create or update StoredFile record for filesystem file.
        
        Returns:
            Tuple of (object, created) where created is True if new record
        """
        # Calculate parent_path for directory queries
        parent_path = str(Path(path).parent) if "/" in path else ""
        if parent_path == ".":
            parent_path = ""
        
        # Idempotent: update_or_create handles race conditions
        return StoredFile.objects.update_or_create(
            owner=user,
            path=path,
            defaults={
                'name': file_info['name'],
                'size': file_info['size'],
                'content_type': file_info['content_type'],
                'is_directory': file_info['is_directory'],
                'parent_path': parent_path,
                'encryption_method': StoredFile.ENCRYPTION_NONE,
                'sort_position': None,  # Alphabetical
            }
        )
