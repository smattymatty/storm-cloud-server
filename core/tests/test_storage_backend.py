"""Tests for storage backend implementations."""

import tempfile
import shutil
from pathlib import Path
from django.test import TestCase, override_settings
from core.storage.local import LocalStorageBackend
from io import BytesIO


@override_settings(STORAGE_ENCRYPTION_METHOD="none")
class LocalStorageBackendTest(TestCase):
    """Tests for LocalStorageBackend."""

    def setUp(self):
        """Create temp directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.backend = LocalStorageBackend(storage_root=Path(self.temp_dir))

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    def test_save_and_open_file(self):
        """Save and open file should work."""
        content = BytesIO(b"test content")
        self.backend.save("test.txt", content)

        opened_file = self.backend.open("test.txt")
        result = opened_file.read()
        self.assertEqual(result, b"test content")

    def test_mkdir_creates_directory(self):
        """mkdir should create directory."""
        self.backend.mkdir("newdir")
        self.assertTrue((Path(self.temp_dir) / "newdir").is_dir())

    def test_mkdir_creates_nested_directories(self):
        """mkdir should create nested directories."""
        self.backend.mkdir("a/b/c")
        self.assertTrue((Path(self.temp_dir) / "a/b/c").is_dir())

    def test_exists_returns_true_for_file(self):
        """exists should return True for existing file."""
        self.backend.save("exists.txt", BytesIO(b"content"))
        self.assertTrue(self.backend.exists("exists.txt"))

    def test_exists_returns_false_for_missing(self):
        """exists should return False for non-existent path."""
        self.assertFalse(self.backend.exists("missing.txt"))

    def test_delete_removes_file(self):
        """delete should remove file."""
        self.backend.save("todelete.txt", BytesIO(b"content"))
        self.backend.delete("todelete.txt")
        self.assertFalse(self.backend.exists("todelete.txt"))

    def test_delete_removes_empty_directory(self):
        """delete should remove empty directory."""
        self.backend.mkdir("emptydir")
        self.backend.delete("emptydir")
        self.assertFalse(self.backend.exists("emptydir"))

    def test_list_returns_directory_contents(self):
        """list should return directory contents."""
        self.backend.mkdir("testdir")
        self.backend.save("testdir/file1.txt", BytesIO(b"1"))
        self.backend.save("testdir/file2.txt", BytesIO(b"2"))
        self.backend.mkdir("testdir/subdir")

        items = list(self.backend.list("testdir"))
        names = [item.name for item in items]

        self.assertIn("file1.txt", names)
        self.assertIn("file2.txt", names)
        self.assertIn("subdir", names)

    def test_info_returns_file_metadata(self):
        """info should return file metadata."""
        self.backend.save("test.txt", BytesIO(b"content"))
        file_info = self.backend.info("test.txt")

        self.assertEqual(file_info.name, "test.txt")
        self.assertEqual(file_info.size, 7)
        self.assertFalse(file_info.is_directory)

    def test_info_returns_directory_metadata(self):
        """info should return directory metadata."""
        self.backend.mkdir("testdir")
        dir_info = self.backend.info("testdir")

        self.assertEqual(dir_info.name, "testdir")
        self.assertTrue(dir_info.is_directory)
        self.assertEqual(dir_info.size, 0)

    def test_path_traversal_blocked(self):
        """Path traversal attempts should be blocked."""
        with self.assertRaises(ValueError):
            self.backend.save("../etc/passwd", BytesIO(b"bad"))

    def test_save_requires_parent_directory(self):
        """save should fail if parent directory doesn't exist."""
        with self.assertRaises(FileNotFoundError):
            self.backend.save("nonexistent/file.txt", BytesIO(b"content"))

    def test_open_nonexistent_file_raises_error(self):
        """open should raise FileNotFoundError for missing file."""
        with self.assertRaises(FileNotFoundError):
            self.backend.open("nonexistent.txt")

    def test_list_nonexistent_directory_raises_error(self):
        """list should raise FileNotFoundError for missing directory."""
        with self.assertRaises(FileNotFoundError):
            list(self.backend.list("nonexistent"))
