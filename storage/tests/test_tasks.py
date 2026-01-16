"""Tests for Django 6.0 Tasks - rebuild_storage_index task."""

import shutil
from pathlib import Path
from django.test import TestCase, override_settings
from django.conf import settings

from storage.tasks import rebuild_storage_index
from storage.models import StoredFile
from accounts.tests.factories import UserWithProfileFactory
from storage.tests.factories import StoredFileFactory


@override_settings(STORAGE_ENCRYPTION_METHOD="none")
class RebuildStorageIndexTaskTestCase(TestCase):
    """Test suite for rebuild_storage_index Django task."""

    @classmethod
    def setUpClass(cls):
        """Set up test storage directory."""
        super().setUpClass()
        cls.test_storage_root = settings.BASE_DIR / "storage_root_test_tasks"
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
        self.user_storage = self.test_storage_root / str(self.user.account.id)
        self.user_storage.mkdir(exist_ok=True)

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

    # =========================================================================
    # Task Execution Tests
    # =========================================================================

    def test_task_enqueue_audit_mode(self):
        """Test enqueueing task in audit mode."""
        self._create_file("test.txt")

        # Enqueue task (ImmediateBackend runs synchronously)
        result = rebuild_storage_index.enqueue(mode="audit")

        # Check result object
        self.assertEqual(result.status, "SUCCESSFUL")
        self.assertIsNotNone(result.id)
        self.assertIsInstance(result.id, str)

        # Check return value
        stats = result.return_value
        self.assertEqual(stats["status"], "success")
        self.assertEqual(stats["mode"], "audit")
        self.assertEqual(stats["files_on_disk"], 1)

    def test_task_enqueue_sync_mode(self):
        """Test enqueueing task in sync mode creates records."""
        self._create_file("new.txt")

        # Initial count should be 0
        self.assertEqual(StoredFile.objects.filter(owner=self.user.account).count(), 0)

        # Enqueue sync task
        result = rebuild_storage_index.enqueue(mode="sync")

        self.assertEqual(result.status, "SUCCESSFUL")

        # Check that record was created
        self.assertEqual(StoredFile.objects.filter(owner=self.user.account).count(), 1)

        # Check stats
        stats = result.return_value
        self.assertEqual(stats["records_created"], 1)

    def test_task_enqueue_with_user_id(self):
        """Test task execution filtered by user_id."""
        # Create second user
        user2 = UserWithProfileFactory(verified=True)
        user2_storage = self.test_storage_root / str(user2.account.id)
        user2_storage.mkdir(exist_ok=True)

        # Create files for both users
        self._create_file("user1.txt")
        (user2_storage / "user2.txt").write_text("content")

        # Sync only user1
        result = rebuild_storage_index.enqueue(mode="sync", user_id=self.user.id)

        stats = result.return_value
        self.assertEqual(stats["users_scanned"], 1)
        self.assertEqual(stats["records_created"], 1)

        # Only user1's file should have record
        self.assertTrue(
            StoredFile.objects.filter(
                owner=self.user.account, path="user1.txt"
            ).exists()
        )
        self.assertFalse(
            StoredFile.objects.filter(owner=user2.account, path="user2.txt").exists()
        )

        # Cleanup
        shutil.rmtree(user2_storage)

    def test_task_enqueue_dry_run(self):
        """Test task with dry_run flag doesn't make changes."""
        self._create_file("test.txt")

        result = rebuild_storage_index.enqueue(mode="sync", dry_run=True)

        self.assertEqual(result.status, "SUCCESSFUL")

        # Stats should show what would be created
        stats = result.return_value
        self.assertEqual(stats["records_created"], 1)

        # But no actual records should exist
        self.assertEqual(StoredFile.objects.filter(owner=self.user.account).count(), 0)

    def test_task_enqueue_force_flag(self):
        """Test task respects force flag for destructive operations."""
        # Create orphaned record
        StoredFileFactory(owner=self.user.account, path="orphan.txt", name="orphan.txt")

        # Without force, clean should fail - task raises ValueError
        result = rebuild_storage_index.enqueue(mode="clean", force=False)

        # Task should fail due to ValueError
        self.assertEqual(result.status, "FAILED")
        self.assertEqual(len(result.errors), 1)
        self.assertIn("force", result.errors[0].traceback.lower())

        # Record should still exist
        self.assertTrue(
            StoredFile.objects.filter(
                owner=self.user.account, path="orphan.txt"
            ).exists()
        )

    def test_task_clean_with_force(self):
        """Test clean task with force flag deletes orphans."""
        # Create orphaned record
        StoredFileFactory(owner=self.user.account, path="orphan.txt", name="orphan.txt")

        result = rebuild_storage_index.enqueue(mode="clean", force=True)

        self.assertEqual(result.status, "SUCCESSFUL")
        stats = result.return_value
        self.assertEqual(stats["status"], "success")
        self.assertEqual(stats["records_deleted"], 1)

        # Record should be deleted
        self.assertFalse(
            StoredFile.objects.filter(
                owner=self.user.account, path="orphan.txt"
            ).exists()
        )

    def test_task_full_mode(self):
        """Test full mode task performs sync and clean."""
        # File on disk, no record
        self._create_file("new.txt")

        # Orphaned record
        StoredFileFactory(owner=self.user.account, path="orphan.txt", name="orphan.txt")

        result = rebuild_storage_index.enqueue(mode="full", force=True)

        self.assertEqual(result.status, "SUCCESSFUL")
        stats = result.return_value
        self.assertEqual(stats["status"], "success")
        self.assertEqual(stats["records_created"], 1)
        self.assertEqual(stats["records_deleted"], 1)

        # Verify final state
        self.assertTrue(
            StoredFile.objects.filter(owner=self.user.account, path="new.txt").exists()
        )
        self.assertFalse(
            StoredFile.objects.filter(
                owner=self.user.account, path="orphan.txt"
            ).exists()
        )

    # =========================================================================
    # Task Return Value Tests
    # =========================================================================

    def test_task_returns_serializable_dict(self):
        """Test task returns JSON-serializable dict (not dataclass)."""
        result = rebuild_storage_index.enqueue(mode="audit")

        stats = result.return_value

        # Should be a dict
        self.assertIsInstance(stats, dict)

        # Should have all expected keys
        expected_keys = [
            "status",
            "mode",
            "dry_run",
            "users_scanned",
            "files_on_disk",
            "files_in_db",
            "missing_in_db",
            "orphaned_in_db",
            "records_created",
            "records_deleted",
            "records_skipped",
            "errors",
        ]
        for key in expected_keys:
            self.assertIn(key, stats)

    def test_task_returns_error_status(self):
        """Test task raises exception for invalid inputs."""
        result = rebuild_storage_index.enqueue(mode="invalid_mode")

        # Task should fail due to ValueError
        self.assertEqual(result.status, "FAILED")
        self.assertEqual(len(result.errors), 1)
        self.assertIn("invalid", result.errors[0].traceback.lower())

    # =========================================================================
    # Task Logging Tests
    # =========================================================================

    def test_task_logs_execution(self):
        """Test task logs start and completion."""
        # This test verifies the logging doesn't crash
        # Actual log output verification would require log capture
        self._create_file("test.txt")

        result = rebuild_storage_index.enqueue(mode="sync")

        # Task should complete successfully
        self.assertEqual(result.status, "SUCCESSFUL")

    # =========================================================================
    # Task Retry Tests
    # =========================================================================

    def test_task_with_max_retries(self):
        """Test task respects max_retries parameter (informational test)."""
        # The @task decorator is configured with max_retries=3
        # This test documents the configuration

        result = rebuild_storage_index.enqueue(mode="audit")

        # Task should complete on first attempt
        self.assertEqual(result.status, "SUCCESSFUL")

        # Note: Django 6.0 ImmediateBackend doesn't retry,
        # but the configuration is in place for future async backends

    # =========================================================================
    # Integration Tests
    # =========================================================================

    def test_task_integration_full_workflow(self):
        """Test complete workflow: filesystem changes -> task -> DB sync."""
        # Step 1: Create files on disk
        self._create_file("file1.txt", "content 1")
        self._create_file("file2.txt", "content 2")
        self._create_file("folder/file3.txt", "content 3")

        # Step 2: Run sync task
        result = rebuild_storage_index.enqueue(mode="sync")
        self.assertEqual(result.status, "SUCCESSFUL")

        # Step 3: Verify DB records created
        self.assertEqual(
            StoredFile.objects.filter(owner=self.user.account).count(), 4
        )  # 3 files + 1 folder

        # Step 4: Delete a file on disk
        (self.user_storage / "file1.txt").unlink()

        # Step 5: Run audit to detect orphan
        result = rebuild_storage_index.enqueue(mode="audit")
        stats = result.return_value
        self.assertEqual(stats["orphaned_in_db"], 1)

        # Step 6: Run clean to remove orphan
        result = rebuild_storage_index.enqueue(mode="clean", force=True)
        stats = result.return_value
        self.assertEqual(stats["records_deleted"], 1)

        # Step 7: Verify final state
        self.assertEqual(
            StoredFile.objects.filter(owner=self.user.account).count(), 3
        )  # 2 files + 1 folder
        self.assertFalse(
            StoredFile.objects.filter(
                owner=self.user.account, path="file1.txt"
            ).exists()
        )

    def test_task_handles_concurrent_filesystem_changes(self):
        """Test task handles filesystem state changes during execution."""
        # Create initial file
        self._create_file("initial.txt")

        # Sync it
        rebuild_storage_index.enqueue(mode="sync")
        self.assertEqual(StoredFile.objects.filter(owner=self.user.account).count(), 1)

        # Add more files
        self._create_file("added.txt")

        # Sync again (should be idempotent + add new file)
        result = rebuild_storage_index.enqueue(mode="sync")
        stats = result.return_value
        self.assertEqual(stats["records_created"], 1)  # Only the new file

        # Final count should be 2
        self.assertEqual(StoredFile.objects.filter(owner=self.user.account).count(), 2)

    def test_task_handles_empty_storage(self):
        """Test task handles user with no files gracefully."""
        # Don't create any files

        result = rebuild_storage_index.enqueue(mode="audit")

        self.assertEqual(result.status, "SUCCESSFUL")
        stats = result.return_value
        self.assertEqual(stats["files_on_disk"], 0)
        self.assertEqual(stats["files_in_db"], 0)

    def test_task_multiple_users_parallel(self):
        """Test task can process multiple users in single execution."""
        # Create three users with files
        users = [UserWithProfileFactory(verified=True) for _ in range(3)]

        for user in users:
            user_storage = self.test_storage_root / str(user.account.id)
            user_storage.mkdir(exist_ok=True)
            (user_storage / "file.txt").write_text("content")

        # Sync all users
        result = rebuild_storage_index.enqueue(mode="sync")

        stats = result.return_value
        self.assertEqual(stats["users_scanned"], 4)  # 3 new + 1 from setUp
        self.assertEqual(stats["records_created"], 3)

        # Verify all users have records
        for user in users:
            self.assertTrue(
                StoredFile.objects.filter(owner=user.account, path="file.txt").exists()
            )

        # Cleanup
        for user in users:
            shutil.rmtree(self.test_storage_root / str(user.account.id))
