"""Tests for encrypt_existing_files management command (ADR 010)."""

import base64
import secrets
import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from core.services.encryption import VERSION_AES_256_GCM, OVERHEAD
from core.storage.local import LocalStorageBackend
from storage.models import StoredFile

User = get_user_model()


def generate_test_key() -> str:
    """Generate a valid encryption key for testing."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


TEST_KEY = generate_test_key()


class EncryptExistingFilesCommandDisabledTest(TestCase):
    """Tests when encryption is disabled."""

    @override_settings(STORAGE_ENCRYPTION_METHOD="none")
    def test_raises_error_when_disabled(self):
        """Command should raise error when encryption disabled."""
        with self.assertRaises(CommandError) as ctx:
            call_command("encrypt_existing_files", "--mode", "audit")

        self.assertIn("Encryption is not enabled", str(ctx.exception))


@override_settings(
    STORAGE_ENCRYPTION_METHOD="server",
    STORAGE_ENCRYPTION_KEY=TEST_KEY,
    STORAGE_ENCRYPTION_KEY_ID="test-key-1",
)
class EncryptExistingFilesCommandTest(TestCase):
    """Tests for encrypt_existing_files command."""

    def setUp(self):
        """Create temp directory and test user."""
        self.temp_dir = tempfile.mkdtemp()
        self.backend = LocalStorageBackend(storage_root=Path(self.temp_dir))
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        # Create user directory
        user_dir = Path(self.temp_dir) / str(self.user.id)
        user_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    def _create_plaintext_file(self, filename: str, content: bytes) -> StoredFile:
        """Create a plaintext file directly on disk and in DB."""
        user_dir = Path(self.temp_dir) / str(self.user.id)
        file_path = user_dir / filename
        file_path.write_bytes(content)

        return StoredFile.objects.create(
            owner=self.user,
            path=filename,
            name=filename,
            size=len(content),
            content_type="text/plain",
            is_directory=False,
            parent_path="",
            encryption_method=StoredFile.ENCRYPTION_NONE,
        )

    def test_audit_mode_lists_unencrypted(self):
        """Audit mode should list unencrypted files."""
        self._create_plaintext_file("test.txt", b"test content")

        out = StringIO()
        with override_settings(STORMCLOUD_STORAGE_ROOT=self.temp_dir):
            call_command(
                "encrypt_existing_files", "--mode", "audit", stdout=out, verbosity=2
            )

        output = out.getvalue()
        self.assertIn("[UNENCRYPTED]", output)
        self.assertIn("test.txt", output)

    def test_audit_mode_reports_count(self):
        """Audit mode should report unencrypted file count."""
        self._create_plaintext_file("file1.txt", b"content 1")
        self._create_plaintext_file("file2.txt", b"content 2")

        out = StringIO()
        with override_settings(STORMCLOUD_STORAGE_ROOT=self.temp_dir):
            call_command("encrypt_existing_files", "--mode", "audit", stdout=out)

        output = out.getvalue()
        self.assertIn("Unencrypted files: 2", output)

    def test_encrypt_mode_requires_force(self):
        """Encrypt mode should require --force flag."""
        with self.assertRaises(CommandError) as ctx:
            call_command("encrypt_existing_files", "--mode", "encrypt")

        self.assertIn("--force", str(ctx.exception))

    def test_encrypt_mode_dry_run(self):
        """Encrypt mode with --dry-run should not modify files."""
        stored_file = self._create_plaintext_file("test.txt", b"test content")

        out = StringIO()
        with override_settings(STORMCLOUD_STORAGE_ROOT=self.temp_dir):
            call_command(
                "encrypt_existing_files",
                "--mode",
                "encrypt",
                "--dry-run",
                stdout=out,
                verbosity=2,
            )

        # File should still be plaintext on disk
        file_path = Path(self.temp_dir) / str(self.user.id) / "test.txt"
        self.assertEqual(file_path.read_bytes(), b"test content")

        # DB should not be updated
        stored_file.refresh_from_db()
        self.assertEqual(stored_file.encryption_method, StoredFile.ENCRYPTION_NONE)

        output = out.getvalue()
        self.assertIn("Would encrypt", output)

    @override_settings(STORMCLOUD_STORAGE_ROOT=None)
    def test_encrypt_mode_encrypts_files(self):
        """Encrypt mode with --force should encrypt files."""
        # Override storage root for this test
        with override_settings(STORMCLOUD_STORAGE_ROOT=self.temp_dir):
            stored_file = self._create_plaintext_file("test.txt", b"test content")

            out = StringIO()
            call_command(
                "encrypt_existing_files",
                "--mode",
                "encrypt",
                "--force",
                stdout=out,
                verbosity=2,
            )

            # File should be encrypted on disk
            file_path = Path(self.temp_dir) / str(self.user.id) / "test.txt"
            raw_content = file_path.read_bytes()
            self.assertEqual(raw_content[0:1], VERSION_AES_256_GCM)

            # DB should be updated
            stored_file.refresh_from_db()
            self.assertEqual(stored_file.encryption_method, StoredFile.ENCRYPTION_SERVER)
            self.assertEqual(stored_file.size, 12)  # Original size
            self.assertEqual(stored_file.encrypted_size, 12 + OVERHEAD)
            self.assertEqual(stored_file.key_id, "test-key-1")

            output = out.getvalue()
            self.assertIn("Encrypting", output)

    def test_user_id_filter(self):
        """--user-id should filter to specific user."""
        other_user = User.objects.create_user(
            username="other", email="other@example.com", password="pass"
        )
        other_dir = Path(self.temp_dir) / str(other_user.id)
        other_dir.mkdir(parents=True, exist_ok=True)

        # Create files for both users
        self._create_plaintext_file("user1_file.txt", b"user 1 content")

        other_file_path = other_dir / "user2_file.txt"
        other_file_path.write_bytes(b"user 2 content")
        StoredFile.objects.create(
            owner=other_user,
            path="user2_file.txt",
            name="user2_file.txt",
            size=14,
            is_directory=False,
            parent_path="",
            encryption_method=StoredFile.ENCRYPTION_NONE,
        )

        out = StringIO()
        with override_settings(STORMCLOUD_STORAGE_ROOT=self.temp_dir):
            call_command(
                "encrypt_existing_files",
                "--mode",
                "audit",
                "--user-id",
                str(self.user.id),
                stdout=out,
            )

        output = out.getvalue()
        self.assertIn("Users scanned: 1", output)
        self.assertIn("Unencrypted files: 1", output)

    def test_skips_directories(self):
        """Command should skip directory entries."""
        # Create a directory entry
        user_dir = Path(self.temp_dir) / str(self.user.id) / "mydir"
        user_dir.mkdir(parents=True, exist_ok=True)
        StoredFile.objects.create(
            owner=self.user,
            path="mydir",
            name="mydir",
            size=0,
            is_directory=True,
            parent_path="",
            encryption_method=StoredFile.ENCRYPTION_NONE,
        )

        out = StringIO()
        with override_settings(STORMCLOUD_STORAGE_ROOT=self.temp_dir):
            call_command("encrypt_existing_files", "--mode", "audit", stdout=out)

        output = out.getvalue()
        self.assertIn("Files scanned: 0", output)  # Directories not counted

    def test_skips_already_encrypted(self):
        """Command should skip already encrypted files."""
        # Create an encrypted file via the backend
        from io import BytesIO
        user_prefix = str(self.user.id)
        content = BytesIO(b"encrypted content")

        with override_settings(STORMCLOUD_STORAGE_ROOT=self.temp_dir):
            backend = LocalStorageBackend(storage_root=Path(self.temp_dir))
            file_info = backend.save(f"{user_prefix}/encrypted.txt", content)

        StoredFile.objects.create(
            owner=self.user,
            path="encrypted.txt",
            name="encrypted.txt",
            size=file_info.size,
            encrypted_size=file_info.encrypted_size,
            is_directory=False,
            parent_path="",
            encryption_method=StoredFile.ENCRYPTION_SERVER,
            key_id=file_info.encryption_key_id,
        )

        out = StringIO()
        with override_settings(STORMCLOUD_STORAGE_ROOT=self.temp_dir):
            call_command(
                "encrypt_existing_files", "--mode", "audit", stdout=out, verbosity=2
            )

        output = out.getvalue()
        self.assertIn("Already encrypted: 1", output)
        self.assertIn("Unencrypted files: 0", output)

    def test_invalid_user_id_raises_error(self):
        """Invalid --user-id should raise error."""
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "encrypt_existing_files", "--mode", "audit", "--user-id", "99999"
            )

        self.assertIn("not found", str(ctx.exception))

    def test_summary_shows_all_encrypted(self):
        """Summary should show success message when all files encrypted."""
        # Create already encrypted file (DB only - no physical file needed)
        StoredFile.objects.create(
            owner=self.user,
            path="encrypted.txt",
            name="encrypted.txt",
            size=100,
            is_directory=False,
            parent_path="",
            encryption_method=StoredFile.ENCRYPTION_SERVER,
        )

        out = StringIO()
        with override_settings(STORMCLOUD_STORAGE_ROOT=self.temp_dir):
            call_command("encrypt_existing_files", "--mode", "audit", stdout=out)

        output = out.getvalue()
        self.assertIn("All files are encrypted", output)
