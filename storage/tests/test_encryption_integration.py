"""Integration tests for storage encryption (ADR 010)."""

import base64
import secrets
import shutil
import tempfile
from io import BytesIO
from pathlib import Path

from django.test import TestCase, override_settings

from core.services.encryption import VERSION_AES_256_GCM, EncryptionService, OVERHEAD
from core.storage.local import LocalStorageBackend


def generate_test_key() -> str:
    """Generate a valid encryption key for testing."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


TEST_KEY = generate_test_key()


class LocalStorageBackendEncryptionDisabledTest(TestCase):
    """Tests for storage backend when encryption is disabled."""

    def setUp(self):
        """Create temp directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.backend = LocalStorageBackend(storage_root=Path(self.temp_dir))

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    @override_settings(STORAGE_ENCRYPTION_METHOD="none")
    def test_save_stores_plaintext(self):
        """save should store plaintext when encryption disabled."""
        content = BytesIO(b"test content")
        self.backend.save("test.txt", content)

        # Read raw file to verify plaintext
        raw_path = Path(self.temp_dir) / "test.txt"
        self.assertEqual(raw_path.read_bytes(), b"test content")

    @override_settings(STORAGE_ENCRYPTION_METHOD="none")
    def test_open_returns_plaintext(self):
        """open should return plaintext content."""
        content = BytesIO(b"test content")
        self.backend.save("test.txt", content)

        file_handle = self.backend.open("test.txt")
        self.assertEqual(file_handle.read(), b"test content")

    @override_settings(STORAGE_ENCRYPTION_METHOD="none")
    def test_file_info_no_encryption_metadata(self):
        """FileInfo should have encryption_method='none' when disabled."""
        content = BytesIO(b"test content")
        file_info = self.backend.save("test.txt", content)

        self.assertEqual(file_info.encryption_method, "none")
        self.assertIsNone(file_info.encrypted_size)
        self.assertIsNone(file_info.encryption_key_id)


@override_settings(
    STORAGE_ENCRYPTION_METHOD="server",
    STORAGE_ENCRYPTION_KEY=TEST_KEY,
    STORAGE_ENCRYPTION_KEY_ID="test-key-1",
)
class LocalStorageBackendEncryptionEnabledTest(TestCase):
    """Tests for storage backend when encryption is enabled."""

    def setUp(self):
        """Create temp directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.backend = LocalStorageBackend(storage_root=Path(self.temp_dir))

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    def test_save_encrypts_content(self):
        """save should encrypt content on disk."""
        content = BytesIO(b"test content")
        self.backend.save("test.txt", content)

        # Read raw file to verify encryption
        raw_path = Path(self.temp_dir) / "test.txt"
        raw_content = raw_path.read_bytes()

        # Should have version byte
        self.assertEqual(raw_content[0:1], VERSION_AES_256_GCM)

        # Should NOT be plaintext
        self.assertNotEqual(raw_content, b"test content")

    def test_open_decrypts_content(self):
        """open should decrypt and return original content."""
        content = BytesIO(b"test content")
        self.backend.save("test.txt", content)

        file_handle = self.backend.open("test.txt")
        self.assertEqual(file_handle.read(), b"test content")

    def test_save_returns_correct_sizes(self):
        """save should return original size and encrypted size."""
        content = BytesIO(b"test content")  # 12 bytes
        file_info = self.backend.save("test.txt", content)

        self.assertEqual(file_info.size, 12)  # Original size
        self.assertEqual(file_info.encrypted_size, 12 + OVERHEAD)

    def test_file_info_has_encryption_metadata(self):
        """FileInfo should have encryption metadata when enabled."""
        content = BytesIO(b"test content")
        file_info = self.backend.save("test.txt", content)

        self.assertEqual(file_info.encryption_method, "server")
        self.assertEqual(file_info.encryption_key_id, "test-key-1")

    def test_open_raw_bypasses_decryption(self):
        """open_raw should return encrypted content without decryption."""
        content = BytesIO(b"test content")
        self.backend.save("test.txt", content)

        raw_handle = self.backend.open_raw("test.txt")
        raw_content = raw_handle.read()

        # Should have version byte (encrypted)
        self.assertEqual(raw_content[0:1], VERSION_AES_256_GCM)

    def test_save_empty_file(self):
        """save should handle empty files."""
        content = BytesIO(b"")
        file_info = self.backend.save("empty.txt", content)

        self.assertEqual(file_info.size, 0)
        self.assertEqual(file_info.encrypted_size, OVERHEAD)

        # Verify roundtrip
        file_handle = self.backend.open("empty.txt")
        self.assertEqual(file_handle.read(), b"")

    def test_save_large_file(self):
        """save should handle large files."""
        large_content = b"x" * (1024 * 1024)  # 1 MB
        content = BytesIO(large_content)
        file_info = self.backend.save("large.bin", content)

        self.assertEqual(file_info.size, 1024 * 1024)

        # Verify roundtrip
        file_handle = self.backend.open("large.bin")
        self.assertEqual(file_handle.read(), large_content)


@override_settings(
    STORAGE_ENCRYPTION_METHOD="server",
    STORAGE_ENCRYPTION_KEY=TEST_KEY,
    STORAGE_ENCRYPTION_KEY_ID="1",
)
class LocalStorageBackendMixedModeTest(TestCase):
    """Tests for mixed mode (plaintext files when encryption enabled)."""

    def setUp(self):
        """Create temp directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.backend = LocalStorageBackend(storage_root=Path(self.temp_dir))

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    def test_open_plaintext_file(self):
        """open should return plaintext content for unencrypted files."""
        # Write plaintext directly to disk (simulating pre-encryption file)
        raw_path = Path(self.temp_dir) / "legacy.txt"
        raw_path.write_bytes(b"legacy plaintext content")

        # Backend should detect and return plaintext
        file_handle = self.backend.open("legacy.txt")
        self.assertEqual(file_handle.read(), b"legacy plaintext content")

    def test_open_plaintext_file_starting_with_different_byte(self):
        """open should detect plaintext even if first byte differs from version."""
        # Ensure first byte is not VERSION_AES_256_GCM
        plaintext = b"Plain text starting with P"
        raw_path = Path(self.temp_dir) / "plain.txt"
        raw_path.write_bytes(plaintext)

        file_handle = self.backend.open("plain.txt")
        self.assertEqual(file_handle.read(), plaintext)

    def test_info_returns_disk_size_for_plaintext(self):
        """info should return disk size for plaintext files."""
        plaintext = b"some content"
        raw_path = Path(self.temp_dir) / "plain.txt"
        raw_path.write_bytes(plaintext)

        file_info = self.backend.info("plain.txt")
        self.assertEqual(file_info.size, len(plaintext))


@override_settings(
    STORAGE_ENCRYPTION_METHOD="server",
    STORAGE_ENCRYPTION_KEY=TEST_KEY,
)
class EncryptionServiceIntegrationTest(TestCase):
    """Integration tests for EncryptionService with storage backend."""

    def setUp(self):
        """Create temp directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.backend = LocalStorageBackend(storage_root=Path(self.temp_dir))

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    def test_backend_encryption_service_initialized(self):
        """Backend should initialize encryption service."""
        self.assertIsInstance(self.backend.encryption, EncryptionService)

    def test_backend_uses_settings(self):
        """Backend's encryption service should use settings."""
        self.assertTrue(self.backend.encryption.is_enabled)
        self.assertEqual(self.backend.encryption.method, "server")
