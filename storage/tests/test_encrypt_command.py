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
from accounts.models import Account, Organization

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
        self.shared_dir = tempfile.mkdtemp()
        self.backend = LocalStorageBackend(
            storage_root=Path(self.temp_dir),
            shared_root=Path(self.shared_dir),
        )
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        # Create organization and account for the user
        org = Organization.objects.create(name="Test Org", slug="test-org-encrypt")
        self.account = Account.objects.create(
            user=self.user, organization=org, email_verified=True
        )
        # Create user directory
        user_dir = Path(self.temp_dir) / str(self.account.id)
        user_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up temp directories."""
        shutil.rmtree(self.temp_dir)
        shutil.rmtree(self.shared_dir)

    def _create_plaintext_file(self, filename: str, content: bytes) -> StoredFile:
        """Create a plaintext file directly on disk and in DB."""
        user_dir = Path(self.temp_dir) / str(self.account.id)
        file_path = user_dir / filename
        file_path.write_bytes(content)

        return StoredFile.objects.create(
            owner=self.account,
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
        with override_settings(
            STORMCLOUD_STORAGE_ROOT=self.temp_dir,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.shared_dir,
        ):
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
        with override_settings(
            STORMCLOUD_STORAGE_ROOT=self.temp_dir,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.shared_dir,
        ):
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
        with override_settings(
            STORMCLOUD_STORAGE_ROOT=self.temp_dir,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.shared_dir,
        ):
            call_command(
                "encrypt_existing_files",
                "--mode",
                "encrypt",
                "--dry-run",
                stdout=out,
                verbosity=2,
            )

        # File should still be plaintext on disk
        file_path = Path(self.temp_dir) / str(self.account.id) / "test.txt"
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
        with override_settings(
            STORMCLOUD_STORAGE_ROOT=self.temp_dir,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.shared_dir,
        ):
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
            file_path = Path(self.temp_dir) / str(self.account.id) / "test.txt"
            raw_content = file_path.read_bytes()
            self.assertEqual(raw_content[0:1], VERSION_AES_256_GCM)

            # DB should be updated
            stored_file.refresh_from_db()
            self.assertEqual(
                stored_file.encryption_method, StoredFile.ENCRYPTION_SERVER
            )
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
        other_org = Organization.objects.create(name="Other Org", slug="other-org")
        other_account = Account.objects.create(
            user=other_user, organization=other_org, email_verified=True
        )
        other_dir = Path(self.temp_dir) / str(other_account.id)
        other_dir.mkdir(parents=True, exist_ok=True)

        # Create files for both users
        self._create_plaintext_file("user1_file.txt", b"user 1 content")

        other_file_path = other_dir / "user2_file.txt"
        other_file_path.write_bytes(b"user 2 content")
        StoredFile.objects.create(
            owner=other_account,
            path="user2_file.txt",
            name="user2_file.txt",
            size=14,
            is_directory=False,
            parent_path="",
            encryption_method=StoredFile.ENCRYPTION_NONE,
        )

        out = StringIO()
        with override_settings(
            STORMCLOUD_STORAGE_ROOT=self.temp_dir,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.shared_dir,
        ):
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
        user_dir = Path(self.temp_dir) / str(self.account.id) / "mydir"
        user_dir.mkdir(parents=True, exist_ok=True)
        StoredFile.objects.create(
            owner=self.account,
            path="mydir",
            name="mydir",
            size=0,
            is_directory=True,
            parent_path="",
            encryption_method=StoredFile.ENCRYPTION_NONE,
        )

        out = StringIO()
        with override_settings(
            STORMCLOUD_STORAGE_ROOT=self.temp_dir,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.shared_dir,
        ):
            call_command("encrypt_existing_files", "--mode", "audit", stdout=out)

        output = out.getvalue()
        self.assertIn("Files scanned: 0", output)  # Directories not counted

    def test_skips_already_encrypted(self):
        """Command should skip already encrypted files."""
        # Create an encrypted file via the backend
        from io import BytesIO

        user_prefix = str(self.account.id)
        content = BytesIO(b"encrypted content")

        with override_settings(
            STORMCLOUD_STORAGE_ROOT=self.temp_dir,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.shared_dir,
        ):
            backend = LocalStorageBackend(storage_root=Path(self.temp_dir))
            file_info = backend.save(f"{user_prefix}/encrypted.txt", content)

        StoredFile.objects.create(
            owner=self.account,
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
        with override_settings(
            STORMCLOUD_STORAGE_ROOT=self.temp_dir,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.shared_dir,
        ):
            call_command(
                "encrypt_existing_files", "--mode", "audit", stdout=out, verbosity=2
            )

        output = out.getvalue()
        self.assertIn("Already encrypted: 1", output)
        self.assertIn("Unencrypted files: 0", output)

    def test_invalid_user_id_raises_error(self):
        """Invalid --user-id should raise error."""
        with override_settings(
            STORMCLOUD_STORAGE_ROOT=self.temp_dir,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.shared_dir,
        ):
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "encrypt_existing_files", "--mode", "audit", "--user-id", "99999"
                )

            self.assertIn("not found", str(ctx.exception))

    def test_summary_shows_all_encrypted(self):
        """Summary should show success message when all files encrypted."""
        # Create already encrypted file (DB only - no physical file needed)
        StoredFile.objects.create(
            owner=self.account,
            path="encrypted.txt",
            name="encrypted.txt",
            size=100,
            is_directory=False,
            parent_path="",
            encryption_method=StoredFile.ENCRYPTION_SERVER,
        )

        out = StringIO()
        with override_settings(
            STORMCLOUD_STORAGE_ROOT=self.temp_dir,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.shared_dir,
        ):
            call_command("encrypt_existing_files", "--mode", "audit", stdout=out)

        output = out.getvalue()
        self.assertIn("All files are encrypted", output)


@override_settings(
    STORAGE_ENCRYPTION_METHOD="server",
    STORAGE_ENCRYPTION_KEY=TEST_KEY,
    STORAGE_ENCRYPTION_KEY_ID="test-key-1",
)
class EncryptExistingFilesOrgCommandTest(TestCase):
    """Tests for encrypt_existing_files command with org/shared files."""

    def setUp(self):
        """Create temp directories, test user, and test org."""
        self.temp_dir = tempfile.mkdtemp()
        self.shared_dir = tempfile.mkdtemp()
        self.backend = LocalStorageBackend(
            storage_root=Path(self.temp_dir),
            shared_root=Path(self.shared_dir),
        )
        # Create organization
        self.org = Organization.objects.create(
            name="Test Org Encrypt", slug="test-org-encrypt-cmd"
        )
        # Create user and account
        self.user = User.objects.create_user(
            username="orguser", email="orguser@example.com", password="testpass"
        )
        self.account = Account.objects.create(
            user=self.user, organization=self.org, email_verified=True
        )
        # Create org directory in shared storage
        org_dir = Path(self.shared_dir) / str(self.org.id)
        org_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up temp directories."""
        shutil.rmtree(self.temp_dir)
        shutil.rmtree(self.shared_dir)

    def _create_shared_plaintext_file(
        self, filename: str, content: bytes
    ) -> StoredFile:
        """Create a plaintext shared file directly on disk and in DB."""
        org_dir = Path(self.shared_dir) / str(self.org.id)
        file_path = org_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)

        return StoredFile.objects.create(
            organization=self.org,
            path=filename,
            name=filename,
            size=len(content),
            content_type="text/plain",
            is_directory=False,
            parent_path="",
            encryption_method=StoredFile.ENCRYPTION_NONE,
        )

    def test_audit_mode_lists_unencrypted_org_files(self):
        """Audit mode should list unencrypted org files."""
        self._create_shared_plaintext_file("org_test.txt", b"org test content")

        out = StringIO()
        with override_settings(
            STORMCLOUD_STORAGE_ROOT=self.temp_dir,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.shared_dir,
        ):
            call_command(
                "encrypt_existing_files", "--mode", "audit", stdout=out, verbosity=2
            )

        output = out.getvalue()
        self.assertIn("[UNENCRYPTED]", output)
        self.assertIn("org_test.txt", output)
        self.assertIn("Organization Files:", output)

    def test_encrypt_org_files_with_force(self):
        """Encrypt mode with --force should encrypt org files."""
        stored_file = self._create_shared_plaintext_file(
            "org_encrypt.txt", b"secret org data"
        )

        with override_settings(
            STORMCLOUD_STORAGE_ROOT=self.temp_dir,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.shared_dir,
        ):
            call_command(
                "encrypt_existing_files",
                "--mode",
                "encrypt",
                "--force",
            )

        # Check file is encrypted on disk
        file_path = Path(self.shared_dir) / str(self.org.id) / "org_encrypt.txt"
        raw_content = file_path.read_bytes()
        self.assertEqual(raw_content[0:1], VERSION_AES_256_GCM)

        # DB should be updated
        stored_file.refresh_from_db()
        self.assertEqual(stored_file.encryption_method, StoredFile.ENCRYPTION_SERVER)
        self.assertEqual(stored_file.size, 15)  # Original size
        self.assertEqual(stored_file.encrypted_size, 15 + OVERHEAD)
        self.assertEqual(stored_file.key_id, "test-key-1")

    def test_org_id_filter(self):
        """--org-id should filter to specific organization."""
        # Create second org
        org2 = Organization.objects.create(name="Other Org", slug="other-org-encrypt")
        org2_dir = Path(self.shared_dir) / str(org2.id)
        org2_dir.mkdir(parents=True, exist_ok=True)

        # Create files in both orgs
        self._create_shared_plaintext_file("org1_file.txt", b"org1 content")

        (org2_dir / "org2_file.txt").write_bytes(b"org2 content")
        StoredFile.objects.create(
            organization=org2,
            path="org2_file.txt",
            name="org2_file.txt",
            size=12,
            content_type="text/plain",
            is_directory=False,
            parent_path="",
            encryption_method=StoredFile.ENCRYPTION_NONE,
        )

        out = StringIO()
        with override_settings(
            STORMCLOUD_STORAGE_ROOT=self.temp_dir,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.shared_dir,
        ):
            call_command(
                "encrypt_existing_files",
                "--mode",
                "audit",
                "--org-id",
                str(self.org.id),
                stdout=out,
            )

        output = out.getvalue()
        self.assertIn("Organizations scanned: 1", output)
        self.assertIn("Unencrypted files: 1", output)

    def test_orgs_only_skips_user_files(self):
        """--orgs-only flag should skip user files."""
        # Create user directory and file
        user_dir = Path(self.temp_dir) / str(self.account.id)
        user_dir.mkdir(parents=True, exist_ok=True)
        (user_dir / "user_file.txt").write_bytes(b"user content")
        StoredFile.objects.create(
            owner=self.account,
            path="user_file.txt",
            name="user_file.txt",
            size=12,
            is_directory=False,
            parent_path="",
            encryption_method=StoredFile.ENCRYPTION_NONE,
        )

        # Create org file
        self._create_shared_plaintext_file("org_file.txt", b"org content")

        out = StringIO()
        with override_settings(
            STORMCLOUD_STORAGE_ROOT=self.temp_dir,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.shared_dir,
        ):
            call_command(
                "encrypt_existing_files",
                "--mode",
                "audit",
                "--orgs-only",
                stdout=out,
            )

        output = out.getvalue()
        # Should only process org files
        self.assertIn("Organizations scanned: 1", output)
        self.assertNotIn("Users scanned:", output)

    def test_users_only_skips_org_files(self):
        """--users-only flag should skip org files."""
        # Create user directory and file
        user_dir = Path(self.temp_dir) / str(self.account.id)
        user_dir.mkdir(parents=True, exist_ok=True)
        (user_dir / "user_file.txt").write_bytes(b"user content")
        StoredFile.objects.create(
            owner=self.account,
            path="user_file.txt",
            name="user_file.txt",
            size=12,
            is_directory=False,
            parent_path="",
            encryption_method=StoredFile.ENCRYPTION_NONE,
        )

        # Create org file
        self._create_shared_plaintext_file("org_file.txt", b"org content")

        out = StringIO()
        with override_settings(
            STORMCLOUD_STORAGE_ROOT=self.temp_dir,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.shared_dir,
        ):
            call_command(
                "encrypt_existing_files",
                "--mode",
                "audit",
                "--users-only",
                stdout=out,
            )

        output = out.getvalue()
        # Should only process user files
        self.assertIn("Users scanned:", output)
        self.assertNotIn("Organizations scanned:", output)

    def test_mutually_exclusive_flags(self):
        """--users-only and --orgs-only should be mutually exclusive."""
        with override_settings(
            STORMCLOUD_STORAGE_ROOT=self.temp_dir,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.shared_dir,
        ):
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "encrypt_existing_files",
                    "--mode",
                    "audit",
                    "--users-only",
                    "--orgs-only",
                )

            self.assertIn(
                "Cannot use --users-only with --orgs-only", str(ctx.exception)
            )

    def test_invalid_org_id_raises_error(self):
        """Invalid --org-id should raise error."""
        with override_settings(
            STORMCLOUD_STORAGE_ROOT=self.temp_dir,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.shared_dir,
        ):
            with self.assertRaises(CommandError) as ctx:
                # Use a valid UUID format that doesn't exist
                call_command(
                    "encrypt_existing_files",
                    "--mode",
                    "audit",
                    "--org-id",
                    "00000000-0000-0000-0000-000000000000",
                )

            self.assertIn("not found", str(ctx.exception))

    def test_skips_already_encrypted_org_files(self):
        """Command should skip already encrypted org files."""
        from io import BytesIO

        # Create an encrypted file via the backend
        content = BytesIO(b"encrypted org content")

        with override_settings(
            STORMCLOUD_STORAGE_ROOT=self.temp_dir,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.shared_dir,
        ):
            backend = LocalStorageBackend(
                storage_root=Path(self.temp_dir),
                shared_root=Path(self.shared_dir),
            )
            file_info = backend.save_shared(self.org.id, "encrypted_org.txt", content)

        StoredFile.objects.create(
            organization=self.org,
            path="encrypted_org.txt",
            name="encrypted_org.txt",
            size=file_info.size,
            encrypted_size=file_info.encrypted_size,
            is_directory=False,
            parent_path="",
            encryption_method=StoredFile.ENCRYPTION_SERVER,
            key_id=file_info.encryption_key_id,
        )

        out = StringIO()
        with override_settings(
            STORMCLOUD_STORAGE_ROOT=self.temp_dir,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.shared_dir,
        ):
            call_command(
                "encrypt_existing_files",
                "--mode",
                "audit",
                "--orgs-only",
                stdout=out,
                verbosity=2,
            )

        output = out.getvalue()
        self.assertIn("Already encrypted: 1", output)
        self.assertIn("Unencrypted files: 0", output)
