"""Tests for BulkOperationService."""

import shutil
from pathlib import Path
from django.test import TestCase, override_settings
from django.conf import settings

from core.services.bulk import BulkOperationService, BulkOperationStats
from core.storage.local import LocalStorageBackend
from storage.models import StoredFile
from accounts.tests.factories import UserWithProfileFactory
from storage.tests.factories import StoredFileFactory


class BulkOperationServiceTestCase(TestCase):
    """Test suite for BulkOperationService."""

    @classmethod
    def setUpClass(cls):
        """Set up test storage directory."""
        super().setUpClass()
        cls.test_storage_root = settings.BASE_DIR / "storage_root_test_bulk"
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

        # Create user storage directory (use Account UUID, not User ID)
        self.user_storage = self.test_storage_root / str(self.user.account.id)
        self.user_storage.mkdir(exist_ok=True)

        # Create service
        self.backend = LocalStorageBackend()
        self.service = BulkOperationService(
            account=self.user.account, backend=self.backend
        )

    def tearDown(self):
        """Clean up test-specific storage."""
        super().tearDown()
        self.settings_override.disable()

        # Clean up user storage directory
        if self.user_storage.exists():
            shutil.rmtree(self.user_storage)

    def _create_file(self, path: str, content: str = "test content") -> Path:
        """Helper to create a file on disk and in DB."""
        file_path = self.user_storage / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

        # Create DB record
        parent_path = str(Path(path).parent) if "/" in path else ""
        if parent_path == ".":
            parent_path = ""

        StoredFile.objects.create(
            owner=self.user.account,
            path=path,
            name=Path(path).name,
            size=len(content),
            content_type="text/plain",
            is_directory=False,
            parent_path=parent_path,
            encryption_method="none",
        )

        return file_path

    def _create_directory(self, path: str) -> Path:
        """Helper to create a directory on disk and in DB."""
        dir_path = self.user_storage / path
        dir_path.mkdir(parents=True, exist_ok=True)

        # Create DB record
        parent_path = str(Path(path).parent) if "/" in path else ""
        if parent_path == ".":
            parent_path = ""

        StoredFile.objects.create(
            owner=self.user.account,
            path=path,
            name=Path(path).name,
            size=0,
            content_type="",
            is_directory=True,
            parent_path=parent_path,
            encryption_method="none",
        )

        return dir_path

    # =========================================================================
    # Validation Tests
    # =========================================================================

    def test_validate_invalid_operation(self):
        """Test that invalid operations raise ValueError."""
        with self.assertRaises(ValueError) as cm:
            self.service.execute(operation="invalid", paths=["file.txt"])

        self.assertIn("Invalid operation", str(cm.exception))

    def test_validate_empty_paths(self):
        """Test that empty paths array raises ValueError."""
        with self.assertRaises(ValueError) as cm:
            self.service.execute(operation="delete", paths=[])

        self.assertIn("cannot be empty", str(cm.exception))

    def test_validate_too_many_paths(self):
        """Test that >250 paths raises ValueError."""
        paths = [f"file{i}.txt" for i in range(251)]

        with self.assertRaises(ValueError) as cm:
            self.service.execute(operation="delete", paths=paths)

        self.assertIn("Maximum 250 paths", str(cm.exception))

    def test_validate_paths_not_list(self):
        """Test that paths must be a list."""
        with self.assertRaises(ValueError) as cm:
            self.service.execute(operation="delete", paths="not-a-list")  # type: ignore

        self.assertIn("must be an array", str(cm.exception))

    def test_validate_paths_not_strings(self):
        """Test that all paths must be strings."""
        with self.assertRaises(ValueError) as cm:
            self.service.execute(operation="delete", paths=["file.txt", 123])  # type: ignore

        self.assertIn("must be strings", str(cm.exception))

    def test_validate_move_requires_destination(self):
        """Test that move operation requires destination."""
        with self.assertRaises(ValueError) as cm:
            self.service.execute(operation="move", paths=["file.txt"])

        self.assertIn("Destination is required", str(cm.exception))

    def test_validate_copy_requires_destination(self):
        """Test that copy operation requires destination."""
        with self.assertRaises(ValueError) as cm:
            self.service.execute(operation="copy", paths=["file.txt"])

        self.assertIn("Destination is required", str(cm.exception))

    # =========================================================================
    # Delete Operation Tests
    # =========================================================================

    def test_delete_single_file(self):
        """Test deleting a single file."""
        self._create_file("test.txt")

        result = self.service.execute(
            operation="delete", paths=["test.txt"], force_sync=True
        )

        self.assertIsInstance(result, BulkOperationStats)
        self.assertEqual(result.operation, "delete")
        self.assertEqual(result.total, 1)
        self.assertEqual(result.succeeded, 1)
        self.assertEqual(result.failed, 0)
        self.assertTrue(result.results[0].success)

        # Verify file deleted from filesystem and DB
        self.assertFalse((self.user_storage / "test.txt").exists())
        self.assertFalse(
            StoredFile.objects.filter(owner=self.user.account, path="test.txt").exists()
        )

    def test_delete_multiple_files(self):
        """Test deleting multiple files."""
        self._create_file("file1.txt")
        self._create_file("file2.txt")
        self._create_file("file3.txt")

        result = self.service.execute(
            operation="delete",
            paths=["file1.txt", "file2.txt", "file3.txt"],
            force_sync=True,
        )

        self.assertEqual(result.total, 3)
        self.assertEqual(result.succeeded, 3)
        self.assertEqual(result.failed, 0)

        # Verify all files deleted
        self.assertEqual(StoredFile.objects.filter(owner=self.user.account).count(), 0)

    def test_delete_directory_recursive(self):
        """Test deleting a directory recursively."""
        self._create_directory("mydir")
        self._create_file("mydir/file1.txt")
        self._create_file("mydir/file2.txt")

        result = self.service.execute(
            operation="delete", paths=["mydir"], force_sync=True
        )

        self.assertEqual(result.succeeded, 1)
        self.assertFalse((self.user_storage / "mydir").exists())

    def test_delete_nonexistent_file(self):
        """Test deleting a file that doesn't exist."""
        result = self.service.execute(
            operation="delete", paths=["missing.txt"], force_sync=True
        )

        self.assertEqual(result.failed, 1)
        self.assertEqual(result.results[0].error_code, "NOT_FOUND")

    def test_delete_partial_success(self):
        """Test that partial failures don't abort batch."""
        self._create_file("good.txt")

        result = self.service.execute(
            operation="delete", paths=["good.txt", "missing.txt"], force_sync=True
        )

        self.assertEqual(result.total, 2)
        self.assertEqual(result.succeeded, 1)
        self.assertEqual(result.failed, 1)

        # Verify good file was deleted
        self.assertFalse(
            StoredFile.objects.filter(owner=self.user.account, path="good.txt").exists()
        )

    def test_delete_duplicate_paths(self):
        """Test that duplicate paths are deduplicated."""
        self._create_file("test.txt")

        result = self.service.execute(
            operation="delete",
            paths=["test.txt", "test.txt", "test.txt"],
            force_sync=True,
        )

        # Should only process once
        self.assertEqual(len(result.results), 1)
        self.assertEqual(result.succeeded, 1)

    # =========================================================================
    # Move Operation Tests
    # =========================================================================

    def test_move_single_file(self):
        """Test moving a single file."""
        self._create_file("source.txt")
        self._create_directory("dest")

        result = self.service.execute(
            operation="move",
            paths=["source.txt"],
            options={"destination": "dest"},
            force_sync=True,
        )

        self.assertEqual(result.succeeded, 1)
        self.assertEqual(result.results[0].data["new_path"], "dest/source.txt")

        # Verify file moved
        self.assertFalse((self.user_storage / "source.txt").exists())
        self.assertTrue((self.user_storage / "dest" / "source.txt").exists())

        # Verify DB updated
        db_file = StoredFile.objects.get(
            owner=self.user.account, path="dest/source.txt"
        )
        self.assertEqual(db_file.parent_path, "dest")

    def test_move_to_root(self):
        """Test moving file to root directory."""
        self._create_directory("subdir")
        self._create_file("subdir/file.txt")

        result = self.service.execute(
            operation="move",
            paths=["subdir/file.txt"],
            options={"destination": ""},
            force_sync=True,
        )

        self.assertEqual(result.succeeded, 1)
        self.assertTrue((self.user_storage / "file.txt").exists())

    def test_move_collision(self):
        """Test moving file when name already exists at destination."""
        self._create_file("source.txt")
        self._create_directory("dest")
        self._create_file("dest/source.txt", "existing")

        result = self.service.execute(
            operation="move",
            paths=["source.txt"],
            options={"destination": "dest"},
            force_sync=True,
        )

        self.assertEqual(result.failed, 1)
        self.assertEqual(result.results[0].error_code, "ALREADY_EXISTS")

    def test_move_nonexistent_source(self):
        """Test moving a file that doesn't exist."""
        self._create_directory("dest")

        result = self.service.execute(
            operation="move",
            paths=["missing.txt"],
            options={"destination": "dest"},
            force_sync=True,
        )

        self.assertEqual(result.failed, 1)
        self.assertEqual(result.results[0].error_code, "NOT_FOUND")

    def test_move_nonexistent_destination(self):
        """Test moving to a destination that doesn't exist."""
        self._create_file("source.txt")

        result = self.service.execute(
            operation="move",
            paths=["source.txt"],
            options={"destination": "missing_dest"},
            force_sync=True,
        )

        self.assertEqual(result.failed, 1)
        self.assertEqual(result.results[0].error_code, "DESTINATION_NOT_FOUND")

    # =========================================================================
    # Copy Operation Tests
    # =========================================================================

    def test_copy_single_file(self):
        """Test copying a single file."""
        self._create_file("source.txt", "content")
        self._create_directory("dest")

        result = self.service.execute(
            operation="copy",
            paths=["source.txt"],
            options={"destination": "dest"},
            force_sync=True,
        )

        self.assertEqual(result.succeeded, 1)
        self.assertEqual(result.results[0].data["new_path"], "dest/source.txt")

        # Verify both files exist
        self.assertTrue((self.user_storage / "source.txt").exists())
        self.assertTrue((self.user_storage / "dest" / "source.txt").exists())

        # Verify DB has both records
        self.assertEqual(
            StoredFile.objects.filter(owner=self.user.account).count(), 3
        )  # source, dest dir, copy

    def test_copy_with_name_collision(self):
        """Test copying file when name exists - should create 'file (copy).txt'."""
        self._create_file("source.txt")
        self._create_directory("dest")
        self._create_file("dest/source.txt", "existing")

        result = self.service.execute(
            operation="copy",
            paths=["source.txt"],
            options={"destination": "dest"},
            force_sync=True,
        )

        self.assertEqual(result.succeeded, 1)

        # Should create a copy with " (copy)" suffix
        new_path = result.results[0].data["new_path"]
        self.assertIn("(copy)", new_path)
        self.assertTrue((self.user_storage / new_path).exists())

    def test_copy_nonexistent_source(self):
        """Test copying a file that doesn't exist."""
        self._create_directory("dest")

        result = self.service.execute(
            operation="copy",
            paths=["missing.txt"],
            options={"destination": "dest"},
            force_sync=True,
        )

        self.assertEqual(result.failed, 1)
        self.assertEqual(result.results[0].error_code, "NOT_FOUND")

    def test_copy_with_quota_check(self):
        """Test that copy respects user quotas."""
        # Set user quota to 100 bytes
        self.user.account.storage_quota_bytes = 100
        self.user.account.save()

        # Create a file that would exceed quota when copied
        self._create_file("large.txt", "x" * 60)  # 60 bytes
        self._create_directory("dest")

        result = self.service.execute(
            operation="copy",
            paths=["large.txt"],
            options={"destination": "dest"},
            force_sync=True,
        )

        # Should fail due to quota
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.results[0].error_code, "QUOTA_EXCEEDED")

    # =========================================================================
    # Async Behavior Tests
    # =========================================================================

    def test_async_threshold_boundary_sync(self):
        """Test that exactly 50 paths runs synchronously."""
        # Create 50 files
        for i in range(50):
            self._create_file(f"file{i}.txt")

        paths = [f"file{i}.txt" for i in range(50)]
        result = self.service.execute(operation="delete", paths=paths)

        # Should be sync (BulkOperationStats, not dict)
        self.assertIsInstance(result, BulkOperationStats)
        self.assertEqual(result.total, 50)

    def test_async_threshold_boundary_async(self):
        """Test that 51 paths triggers async execution (or fallback if Tasks unavailable)."""
        # Create 51 files (but don't run actual async task in test)
        for i in range(51):
            self._create_file(f"file{i}.txt")

        paths = [f"file{i}.txt" for i in range(51)]
        result = self.service.execute(operation="delete", paths=paths)

        # Should be dict response
        self.assertIsInstance(result, dict)

        # If Django Tasks available, should be async with task_id
        # If not available, should be immediate execution fallback
        if result.get("async"):
            assert isinstance(result, dict)  # Type narrowing for mypy
            self.assertIn("task_id", result)
        else:
            # Fallback: immediate execution
            self.assertTrue(result.get("immediate"))
            self.assertEqual(result["total"], 51)

    def test_force_sync_override(self):
        """Test that force_sync bypasses async threshold."""
        # Create 100 files
        for i in range(100):
            self._create_file(f"file{i}.txt")

        paths = [f"file{i}.txt" for i in range(100)]
        result = self.service.execute(operation="delete", paths=paths, force_sync=True)

        # Should be sync despite >50 paths
        self.assertIsInstance(result, BulkOperationStats)
        self.assertEqual(result.total, 100)

    # =========================================================================
    # Edge Cases
    # =========================================================================

    def test_invalid_path_traversal(self):
        """Test that path traversal attempts are rejected."""
        result = self.service.execute(
            operation="delete", paths=["../../../etc/passwd"], force_sync=True
        )

        self.assertEqual(result.failed, 1)
        self.assertEqual(result.results[0].error_code, "INVALID_PATH")
