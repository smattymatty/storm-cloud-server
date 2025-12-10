"""Tests for core utility functions."""

from django.test import TestCase
from core.utils import normalize_path, validate_filename, PathValidationError


class NormalizePathTest(TestCase):
    """Tests for normalize_path function."""

    def test_normalize_path_strips_leading_slashes(self):
        """Leading slashes should be stripped."""
        self.assertEqual(normalize_path('/path/to/file'), 'path/to/file')
        self.assertEqual(normalize_path('///path/to/file'), 'path/to/file')

    def test_normalize_path_strips_trailing_slashes(self):
        """Trailing slashes should be stripped."""
        self.assertEqual(normalize_path('path/to/file/'), 'path/to/file')
        self.assertEqual(normalize_path('path/to/file///'), 'path/to/file')

    def test_normalize_path_collapses_multiple_slashes(self):
        """Multiple consecutive slashes should be collapsed to one."""
        self.assertEqual(normalize_path('path//to///file'), 'path/to/file')

    def test_normalize_path_blocks_traversal(self):
        """Path traversal attempts should raise PathValidationError."""
        with self.assertRaises(PathValidationError):
            normalize_path('../etc/passwd')

        with self.assertRaises(PathValidationError):
            normalize_path('path/../etc')

        with self.assertRaises(PathValidationError):
            normalize_path('path/to/../../../etc')

    def test_normalize_path_blocks_null_bytes(self):
        """Null bytes should raise PathValidationError."""
        with self.assertRaises(PathValidationError):
            normalize_path('path\x00file')

    def test_normalize_path_blocks_control_characters(self):
        """Control characters should raise PathValidationError."""
        with self.assertRaises(PathValidationError):
            normalize_path('path\x01file')

        with self.assertRaises(PathValidationError):
            normalize_path('path\nfile')

    def test_normalize_empty_path(self):
        """Empty path should return empty string."""
        self.assertEqual(normalize_path(''), '')
        self.assertEqual(normalize_path('/'), '')

    def test_normalize_path_preserves_valid_paths(self):
        """Valid paths should be preserved correctly."""
        self.assertEqual(normalize_path('path/to/file.txt'), 'path/to/file.txt')
        self.assertEqual(normalize_path('folder/subfolder'), 'folder/subfolder')


class ValidateFilenameTest(TestCase):
    """Tests for validate_filename function."""

    def test_validate_filename_accepts_valid_names(self):
        """Valid filenames should pass validation."""
        self.assertEqual(validate_filename('file.txt'), 'file.txt')
        self.assertEqual(validate_filename('my-file_123.pdf'), 'my-file_123.pdf')

    def test_validate_filename_rejects_empty(self):
        """Empty filename should raise PathValidationError."""
        with self.assertRaises(PathValidationError):
            validate_filename('')

    def test_validate_filename_rejects_slashes(self):
        """Filenames with slashes should raise PathValidationError."""
        with self.assertRaises(PathValidationError):
            validate_filename('path/file.txt')

        with self.assertRaises(PathValidationError):
            validate_filename('path\\file.txt')

    def test_validate_filename_rejects_dot_names(self):
        """Dot and double-dot should raise PathValidationError."""
        with self.assertRaises(PathValidationError):
            validate_filename('.')

        with self.assertRaises(PathValidationError):
            validate_filename('..')

    def test_validate_filename_rejects_null_bytes(self):
        """Null bytes should raise PathValidationError."""
        with self.assertRaises(PathValidationError):
            validate_filename('file\x00.txt')

    def test_validate_filename_rejects_control_characters(self):
        """Control characters should raise PathValidationError."""
        with self.assertRaises(PathValidationError):
            validate_filename('file\x01.txt')
