"""Tests for IndexSyncService (filesystem-database sync)."""

import shutil
from pathlib import Path
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.conf import settings

from core.services.index_sync import IndexSyncService, IndexSyncStats
from storage.models import StoredFile, ShareLink
from accounts.tests.factories import UserWithProfileFactory
from storage.tests.factories import StoredFileFactory, ShareLinkFactory

User = get_user_model()


class IndexSyncServiceTestCase(TestCase):
    """Test suite for IndexSyncService."""

    @classmethod
    def setUpClass(cls):
        """Set up test storage directory."""
        super().setUpClass()
        cls.test_storage_root = settings.BASE_DIR / 'storage_root_test_index'
        cls.test_storage_root.mkdir(exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        """Clean up test storage directory."""
        super().tearDownClass()
        if cls.test_storage_root.exists():
            shutil.rmtree(cls.test_storage_root)

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.user = UserWithProfileFactory(verified=True)
        
        # Use test storage root
        self.settings_override = override_settings(
            STORMCLOUD_STORAGE_ROOT=self.test_storage_root,
        )
        self.settings_override.enable()
        
        # Create user storage directory
        self.user_storage = self.test_storage_root / str(self.user.id)
        self.user_storage.mkdir(exist_ok=True)
        
        self.service = IndexSyncService()

    def tearDown(self):
        """Clean up test-specific storage."""
        super().tearDown()
        self.settings_override.disable()
        
        # Clean up user storage directory
        if self.user_storage.exists():
            shutil.rmtree(self.user_storage)

    def _create_file(self, path: str, content: str = "test content") -> Path:
        """Helper to create a file on disk."""
        file_path = self.user_storage / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return file_path

    def _create_directory(self, path: str) -> Path:
        """Helper to create a directory on disk."""
        dir_path = self.user_storage / path
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    # =========================================================================
    # Audit Mode Tests
    # =========================================================================

    def test_audit_empty_filesystem_empty_db(self):
        """Test audit with no files on disk and no DB records."""
        stats = self.service.sync(mode='audit')
        
        self.assertEqual(stats.users_scanned, 1)
        self.assertEqual(stats.files_on_disk, 0)
        self.assertEqual(stats.files_in_db, 0)
        self.assertEqual(stats.missing_in_db, 0)
        self.assertEqual(stats.orphaned_in_db, 0)
        self.assertEqual(stats.records_created, 0)
        self.assertEqual(stats.records_deleted, 0)

    def test_audit_files_on_disk_no_db_records(self):
        """Test audit detects missing DB records for files on disk."""
        # Create files on disk
        self._create_file('test1.txt')
        self._create_file('test2.txt')
        self._create_directory('folder1')
        
        stats = self.service.sync(mode='audit')
        
        self.assertEqual(stats.files_on_disk, 3)  # 2 files + 1 directory
        self.assertEqual(stats.files_in_db, 0)
        self.assertEqual(stats.missing_in_db, 3)
        self.assertEqual(stats.orphaned_in_db, 0)
        self.assertEqual(stats.records_created, 0)  # Audit doesn't create

    def test_audit_db_records_no_files_on_disk(self):
        """Test audit detects orphaned DB records with no files on disk."""
        # Create DB records without files
        StoredFileFactory(owner=self.user, path='orphan1.txt', name='orphan1.txt')
        StoredFileFactory(owner=self.user, path='orphan2.txt', name='orphan2.txt')
        
        stats = self.service.sync(mode='audit')
        
        self.assertEqual(stats.files_on_disk, 0)
        self.assertEqual(stats.files_in_db, 2)
        self.assertEqual(stats.missing_in_db, 0)
        self.assertEqual(stats.orphaned_in_db, 2)
        self.assertEqual(stats.records_deleted, 0)  # Audit doesn't delete

    def test_audit_perfect_sync(self):
        """Test audit when filesystem and DB are perfectly synced."""
        # Create file on disk
        self._create_file('synced.txt')
        
        # Create matching DB record
        StoredFileFactory(
            owner=self.user,
            path='synced.txt',
            name='synced.txt',
            size=12,  # len("test content")
            encryption_method='none',
        )
        
        stats = self.service.sync(mode='audit')
        
        self.assertEqual(stats.files_on_disk, 1)
        self.assertEqual(stats.files_in_db, 1)
        self.assertEqual(stats.missing_in_db, 0)
        self.assertEqual(stats.orphaned_in_db, 0)

    def test_audit_mixed_scenario(self):
        """Test audit with mix of synced, missing, and orphaned records."""
        # Synced file
        self._create_file('synced.txt')
        StoredFileFactory(owner=self.user, path='synced.txt', name='synced.txt', size=12)
        
        # File on disk, no DB record
        self._create_file('missing_in_db.txt')
        
        # DB record, no file on disk
        StoredFileFactory(owner=self.user, path='orphaned.txt', name='orphaned.txt')
        
        stats = self.service.sync(mode='audit')
        
        self.assertEqual(stats.files_on_disk, 2)
        self.assertEqual(stats.files_in_db, 2)
        self.assertEqual(stats.missing_in_db, 1)
        self.assertEqual(stats.orphaned_in_db, 1)

    # =========================================================================
    # Sync Mode Tests
    # =========================================================================

    def test_sync_creates_missing_records(self):
        """Test sync mode creates DB records for files on disk."""
        # Create files on disk
        self._create_file('new1.txt', 'content1')
        self._create_file('new2.txt', 'content2')
        
        stats = self.service.sync(mode='sync')
        
        self.assertEqual(stats.records_created, 2)
        
        # Verify DB records were created
        self.assertEqual(StoredFile.objects.filter(owner=self.user).count(), 2)
        
        file1: StoredFile = StoredFile.objects.get(owner=self.user, path='new1.txt')
        self.assertEqual(file1.name, 'new1.txt')
        self.assertEqual(file1.size, 8)  # len("content1")
        self.assertEqual(file1.encryption_method, 'none')
        self.assertFalse(file1.is_directory)

    def test_sync_creates_directory_records(self):
        """Test sync mode creates DB records for directories."""
        self._create_directory('folder1')
        self._create_directory('folder1/subfolder')
        
        stats = self.service.sync(mode='sync')
        
        self.assertEqual(stats.records_created, 2)
        
        # Verify directory records
        folder = StoredFile.objects.get(owner=self.user, path='folder1')
        self.assertTrue(folder.is_directory)
        self.assertEqual(folder.size, 0)
        
        subfolder = StoredFile.objects.get(owner=self.user, path='folder1/subfolder')
        self.assertTrue(subfolder.is_directory)
        self.assertEqual(subfolder.parent_path, 'folder1')

    def test_sync_dry_run_doesnt_create_records(self):
        """Test sync dry-run mode doesn't actually create records."""
        self._create_file('test.txt')
        
        stats = self.service.sync(mode='sync', dry_run=True)
        
        # Stats should show what would be created
        self.assertEqual(stats.records_created, 1)
        
        # But no actual DB records should exist
        self.assertEqual(StoredFile.objects.filter(owner=self.user).count(), 0)

    def test_sync_idempotent(self):
        """Test sync is idempotent (running twice creates same result)."""
        self._create_file('test.txt')
        
        # First sync
        stats1 = self.service.sync(mode='sync')
        self.assertEqual(stats1.records_created, 1)
        
        # Second sync (should not create duplicates)
        stats2 = self.service.sync(mode='sync')
        self.assertEqual(stats2.records_created, 0)
        
        # Should still have exactly 1 record
        self.assertEqual(StoredFile.objects.filter(owner=self.user).count(), 1)

    def test_sync_updates_existing_records(self):
        """Test sync updates size/metadata of existing records."""
        # Create file on disk
        file_path = self._create_file('test.txt', 'initial content')
        
        # Create DB record with wrong size
        StoredFileFactory(
            owner=self.user,
            path='test.txt',
            name='test.txt',
            size=999,  # Wrong size
        )
        
        stats = self.service.sync(mode='sync')
        
        # Should update existing record, not create new one
        self.assertEqual(stats.records_created, 0)  # Updates don't count as creates
        self.assertEqual(StoredFile.objects.filter(owner=self.user).count(), 1)
        
        # Verify size was updated (filesystem wins!)
        record = StoredFile.objects.get(owner=self.user, path='test.txt')
        self.assertEqual(record.size, 15)  # len("initial content")

    def test_sync_nested_directories(self):
        """Test sync handles deeply nested directory structures."""
        self._create_directory('level1')
        self._create_directory('level1/level2')
        self._create_directory('level1/level2/level3')
        self._create_file('level1/level2/level3/deep.txt')
        
        stats = self.service.sync(mode='sync')
        
        self.assertEqual(stats.records_created, 4)  # 3 dirs + 1 file
        
        # Verify parent_path is set correctly
        deep_file = StoredFile.objects.get(owner=self.user, path='level1/level2/level3/deep.txt')
        self.assertEqual(deep_file.parent_path, 'level1/level2/level3')

    # =========================================================================
    # Clean Mode Tests
    # =========================================================================

    def test_clean_deletes_orphaned_records(self):
        """Test clean mode deletes DB records with no files on disk."""
        # Create orphaned DB records
        StoredFileFactory(owner=self.user, path='orphan1.txt', name='orphan1.txt')
        StoredFileFactory(owner=self.user, path='orphan2.txt', name='orphan2.txt')
        
        stats = self.service.sync(mode='clean', force=True)
        
        self.assertEqual(stats.records_deleted, 2)
        self.assertEqual(StoredFile.objects.filter(owner=self.user).count(), 0)

    def test_clean_requires_force(self):
        """Test clean mode requires force flag."""
        StoredFileFactory(owner=self.user, path='orphan.txt', name='orphan.txt')
        
        # Should raise ValueError without force
        with self.assertRaises(ValueError) as cm:
            self.service.sync(mode='clean', force=False)
        
        self.assertIn('force', str(cm.exception).lower())
        
        # Record should still exist
        self.assertEqual(StoredFile.objects.filter(owner=self.user).count(), 1)

    def test_clean_skips_records_with_share_links(self):
        """Test clean mode skips records that have active ShareLinks."""
        # Create orphaned file with ShareLink
        stored_file = StoredFileFactory(owner=self.user, path='shared.txt', name='shared.txt')
        ShareLinkFactory(owner=self.user, stored_file=stored_file)
        
        stats = self.service.sync(mode='clean', force=True)
        
        # Should skip deletion
        self.assertEqual(stats.records_deleted, 0)
        self.assertEqual(stats.records_skipped, 1)
        
        # Record should still exist
        self.assertTrue(StoredFile.objects.filter(owner=self.user, path='shared.txt').exists())

    def test_clean_dry_run_doesnt_delete(self):
        """Test clean dry-run shows what would be deleted without deleting."""
        StoredFileFactory(owner=self.user, path='orphan.txt', name='orphan.txt')
        
        stats = self.service.sync(mode='clean', force=True, dry_run=True)
        
        # Stats should show what would be deleted
        self.assertEqual(stats.records_deleted, 1)
        
        # But record should still exist
        self.assertEqual(StoredFile.objects.filter(owner=self.user).count(), 1)

    def test_clean_preserves_valid_records(self):
        """Test clean mode only deletes orphaned records, keeps valid ones."""
        # Valid record (file exists)
        self._create_file('valid.txt')
        StoredFileFactory(owner=self.user, path='valid.txt', name='valid.txt', size=12)
        
        # Orphaned record (no file)
        StoredFileFactory(owner=self.user, path='orphan.txt', name='orphan.txt')
        
        stats = self.service.sync(mode='clean', force=True)
        
        self.assertEqual(stats.records_deleted, 1)
        
        # Valid record should remain
        self.assertTrue(StoredFile.objects.filter(owner=self.user, path='valid.txt').exists())
        self.assertFalse(StoredFile.objects.filter(owner=self.user, path='orphan.txt').exists())

    # =========================================================================
    # Full Mode Tests
    # =========================================================================

    def test_full_mode_sync_and_clean(self):
        """Test full mode performs both sync and clean operations."""
        # File on disk, no DB record (should sync)
        self._create_file('new.txt')
        
        # DB record, no file on disk (should clean)
        StoredFileFactory(owner=self.user, path='orphan.txt', name='orphan.txt')
        
        # Valid synced file (should remain)
        self._create_file('valid.txt')
        StoredFileFactory(owner=self.user, path='valid.txt', name='valid.txt', size=12)
        
        stats = self.service.sync(mode='full', force=True)
        
        self.assertEqual(stats.records_created, 1)  # new.txt
        self.assertEqual(stats.records_deleted, 1)  # orphan.txt
        
        # Verify final state
        self.assertEqual(StoredFile.objects.filter(owner=self.user).count(), 2)
        self.assertTrue(StoredFile.objects.filter(owner=self.user, path='new.txt').exists())
        self.assertTrue(StoredFile.objects.filter(owner=self.user, path='valid.txt').exists())
        self.assertFalse(StoredFile.objects.filter(owner=self.user, path='orphan.txt').exists())

    def test_full_mode_requires_force(self):
        """Test full mode requires force flag due to clean operation."""
        # Should raise ValueError without force
        with self.assertRaises(ValueError) as cm:
            self.service.sync(mode='full', force=False)
        
        self.assertIn('force', str(cm.exception).lower())

    # =========================================================================
    # User Filtering Tests
    # =========================================================================

    def test_sync_specific_user_only(self):
        """Test syncing only a specific user's files."""
        # Create second user
        user2 = UserWithProfileFactory(verified=True)
        user2_storage = self.test_storage_root / str(user2.id)
        user2_storage.mkdir(exist_ok=True)
        
        # Create files for both users
        self._create_file('user1.txt')
        (user2_storage / 'user2.txt').write_text('content')
        
        # Sync only user1 - create service with specific user_id
        service = IndexSyncService(user_id=self.user.id)
        stats = service.sync(mode='sync')
        
        self.assertEqual(stats.users_scanned, 1)
        self.assertEqual(stats.records_created, 1)
        
        # Only user1's file should have DB record
        self.assertTrue(StoredFile.objects.filter(owner=self.user, path='user1.txt').exists())
        self.assertFalse(StoredFile.objects.filter(owner=user2, path='user2.txt').exists())
        
        # Cleanup
        shutil.rmtree(user2_storage)

    def test_sync_all_users(self):
        """Test syncing all users when no user_id specified."""
        # Create second user
        user2 = UserWithProfileFactory(verified=True)
        user2_storage = self.test_storage_root / str(user2.id)
        user2_storage.mkdir(exist_ok=True)
        
        # Create files for both users
        self._create_file('user1.txt')
        (user2_storage / 'user2.txt').write_text('content')
        
        # Sync all users
        stats = self.service.sync(mode='sync')
        
        self.assertEqual(stats.users_scanned, 2)
        self.assertEqual(stats.records_created, 2)
        
        # Both files should have DB records
        self.assertTrue(StoredFile.objects.filter(owner=self.user, path='user1.txt').exists())
        self.assertTrue(StoredFile.objects.filter(owner=user2, path='user2.txt').exists())
        
        # Cleanup
        shutil.rmtree(user2_storage)

    # =========================================================================
    # Error Handling Tests
    # =========================================================================

    def test_invalid_mode(self):
        """Test error handling for invalid mode."""
        # Should raise ValueError for invalid mode
        with self.assertRaises(ValueError) as cm:
            self.service.sync(mode='invalid_mode')
        
        self.assertIn('invalid', str(cm.exception).lower())

    def test_nonexistent_user_id(self):
        """Test handling of non-existent user ID."""
        # Create service with non-existent user_id
        service = IndexSyncService(user_id=99999)
        stats = service.sync(mode='audit')
        
        # Should handle gracefully (no users scanned)
        self.assertEqual(stats.users_scanned, 0)
        self.assertEqual(stats.files_on_disk, 0)

    def test_filesystem_wins_policy(self):
        """Test that filesystem is always treated as source of truth."""
        # Create file on disk
        self._create_file('truth.txt', 'filesystem content')
        
        # Create DB record with different size
        StoredFileFactory(
            owner=self.user,
            path='truth.txt',
            name='truth.txt',
            size=1,  # Wrong
        )
        
        # Sync should update to match filesystem
        stats = self.service.sync(mode='sync')
        
        record = StoredFile.objects.get(owner=self.user, path='truth.txt')
        self.assertEqual(record.size, 18)  # len("filesystem content") - filesystem wins!

    def test_stats_dataclass(self):
        """Test IndexSyncStats dataclass structure."""
        stats = IndexSyncStats(
            users_scanned=1,
            files_on_disk=5,
            files_in_db=3,
            missing_in_db=2,
            orphaned_in_db=0,
            records_created=0,
            records_deleted=0,
            records_skipped=0,
            errors=[],
        )
        
        self.assertEqual(stats.users_scanned, 1)
        self.assertEqual(stats.files_on_disk, 5)
        self.assertEqual(stats.missing_in_db, 2)
        self.assertIsInstance(stats.errors, list)
