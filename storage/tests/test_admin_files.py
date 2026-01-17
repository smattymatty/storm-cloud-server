"""Tests for admin file endpoints."""

from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status

from accounts.tests.factories import APIKeyFactory, UserWithProfileFactory
from core.tests.base import StormCloudAdminTestCase
from storage.models import FileAuditLog, StoredFile

if TYPE_CHECKING:
    from accounts.typing import UserProtocol as User
else:
    User = get_user_model()


# Disable encryption for admin file tests - they write/read files directly
@override_settings(STORAGE_ENCRYPTION_METHOD="none")
class AdminFileTestCase(StormCloudAdminTestCase):
    """Base test case for admin file tests with encryption disabled."""

    pass


class AdminFileTestMixin:
    """Mixin with helper methods for admin file tests."""

    def _create_file_for_user(
        self, user: User, path: str, content: str = "test content"
    ) -> StoredFile:
        """Create a file in user's storage (filesystem + DB)."""
        storage_path = Path(self.test_storage_root) / str(user.account.id) / path
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_text(content)

        parent_path = str(Path(path).parent) if "/" in path else ""
        if parent_path == ".":
            parent_path = ""

        return StoredFile.objects.create(
            owner=user.account,
            path=path,
            name=Path(path).name,
            size=len(content),
            content_type="text/plain",
            is_directory=False,
            parent_path=parent_path,
            encryption_method="none",
        )

    def _create_dir_for_user(self, user: User, path: str) -> StoredFile:
        """Create a directory in user's storage (filesystem + DB)."""
        storage_path = Path(self.test_storage_root) / str(user.account.id) / path
        storage_path.mkdir(parents=True, exist_ok=True)

        parent_path = str(Path(path).parent) if "/" in path else ""
        if parent_path == ".":
            parent_path = ""

        return StoredFile.objects.create(
            owner=user.account,
            path=path,
            name=Path(path).name,
            size=0,
            content_type="",
            is_directory=True,
            parent_path=parent_path,
            encryption_method="none",
        )

    def _upload_file_as_admin(
        self, user_id: int, path: str, content: bytes = b"test content"
    ):
        """Helper to upload file via admin endpoint."""
        test_file = BytesIO(content)
        test_file.name = Path(path).name
        return self.client.post(
            f"/api/v1/admin/users/{user_id}/files/{path}/upload/",
            {"file": test_file},
        )

    def _assert_audit_log_created(
        self,
        action: str,
        path: str,
        target_user: User,
        performed_by: User | None = None,
        is_admin_action: bool = True,
        success: bool = True,
    ) -> FileAuditLog:
        """Assert that an audit log entry was created with expected values."""
        performed_by = performed_by or self.admin
        # FileAuditLog.target_user and performed_by are ForeignKeys to Account
        log = FileAuditLog.objects.filter(
            action=action,
            path=path,
            target_user=target_user.account,
        ).first()

        self.assertIsNotNone(
            log, f"No audit log found for action={action}, path={path}"
        )
        self.assertEqual(log.performed_by, performed_by.account)
        self.assertEqual(log.is_admin_action, is_admin_action)
        self.assertEqual(log.success, success)
        return log


# =============================================================================
# Directory List Tests
# =============================================================================


class AdminDirectoryListTest(AdminFileTestMixin, AdminFileTestCase):
    """Tests for GET /api/v1/admin/users/{id}/dirs/ and /dirs/{path}/"""

    def setUp(self):
        super().setUp()
        self.target_user = UserWithProfileFactory(verified=True)

    def test_admin_list_user_root_directory(self):
        """Admin can list another user's root directory."""
        # Create some files for target user
        self._create_file_for_user(self.target_user, "file1.txt")
        self._create_file_for_user(self.target_user, "file2.txt")

        response = self.client.get(f"/api/v1/admin/users/{self.target_user.id}/dirs/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 2)
        names = [e["name"] for e in response.data["entries"]]
        self.assertIn("file1.txt", names)
        self.assertIn("file2.txt", names)

    def test_admin_list_user_subdirectory(self):
        """Admin can list subdirectory contents."""
        self._create_dir_for_user(self.target_user, "subdir")
        self._create_file_for_user(self.target_user, "subdir/nested.txt")

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/dirs/subdir/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["path"], "subdir")
        self.assertEqual(response.data["total"], 1)
        self.assertEqual(response.data["entries"][0]["name"], "nested.txt")

    def test_list_nonexistent_user_returns_404(self):
        """Returns 404 for invalid user_id."""
        response = self.client.get("/api/v1/admin/users/99999/dirs/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_admin_gets_403(self):
        """Regular user cannot access admin endpoint."""
        regular_user = UserWithProfileFactory(verified=True)
        regular_key = APIKeyFactory(user=regular_user)
        self.authenticate(api_key=regular_key)

        response = self.client.get(f"/api/v1/admin/users/{self.target_user.id}/dirs/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_creates_audit_log_entry(self):
        """Verify FileAuditLog created with action=list."""
        self._create_file_for_user(self.target_user, "file.txt")

        response = self.client.get(f"/api/v1/admin/users/{self.target_user.id}/dirs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self._assert_audit_log_created(
            action=FileAuditLog.ACTION_LIST,
            path="/",
            target_user=self.target_user,
        )


# =============================================================================
# Directory Create Tests
# =============================================================================


class AdminDirectoryCreateTest(AdminFileTestMixin, AdminFileTestCase):
    """Tests for POST /api/v1/admin/users/{id}/dirs/{path}/create/"""

    def setUp(self):
        super().setUp()
        self.target_user = UserWithProfileFactory(verified=True)

    def test_admin_create_directory_for_user(self):
        """Admin can create directory in user's storage."""
        response = self.client.post(
            f"/api/v1/admin/users/{self.target_user.id}/dirs/newdir/create/"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["path"], "newdir")
        self.assertTrue(response.data["is_directory"])

        # Verify filesystem
        dir_path = (
            Path(self.test_storage_root) / str(self.target_user.account.id) / "newdir"
        )
        self.assertTrue(dir_path.exists())
        self.assertTrue(dir_path.is_dir())

    def test_create_nested_directory(self):
        """Parent directories created as needed."""
        response = self.client.post(
            f"/api/v1/admin/users/{self.target_user.id}/dirs/parent/child/grandchild/create/"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify all directories exist
        base = Path(self.test_storage_root) / str(self.target_user.account.id)
        self.assertTrue((base / "parent" / "child" / "grandchild").exists())

    def test_create_existing_directory_returns_409(self):
        """Conflict if directory exists."""
        self._create_dir_for_user(self.target_user, "existing")

        response = self.client.post(
            f"/api/v1/admin/users/{self.target_user.id}/dirs/existing/create/"
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"]["code"], "ALREADY_EXISTS")

    def test_non_admin_gets_403(self):
        """Regular user cannot access."""
        regular_user = UserWithProfileFactory(verified=True)
        regular_key = APIKeyFactory(user=regular_user)
        self.authenticate(api_key=regular_key)

        response = self.client.post(
            f"/api/v1/admin/users/{self.target_user.id}/dirs/newdir/create/"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_creates_audit_log_entry(self):
        """Verify action=create_dir logged."""
        response = self.client.post(
            f"/api/v1/admin/users/{self.target_user.id}/dirs/auditdir/create/"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self._assert_audit_log_created(
            action=FileAuditLog.ACTION_CREATE_DIR,
            path="auditdir",
            target_user=self.target_user,
        )


# =============================================================================
# File Upload Tests
# =============================================================================


class AdminFileUploadTest(AdminFileTestMixin, AdminFileTestCase):
    """Tests for POST /api/v1/admin/users/{id}/files/{path}/upload/"""

    def setUp(self):
        super().setUp()
        self.target_user = UserWithProfileFactory(verified=True)

    def test_admin_upload_file_to_user(self):
        """Admin can upload file to user's storage."""
        response = self._upload_file_as_admin(
            self.target_user.id, "uploaded.txt", b"admin uploaded content"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "uploaded.txt")
        self.assertEqual(response.data["size"], len(b"admin uploaded content"))

        # Verify filesystem
        file_path = (
            Path(self.test_storage_root)
            / str(self.target_user.account.id)
            / "uploaded.txt"
        )
        self.assertTrue(file_path.exists())
        self.assertEqual(file_path.read_text(), "admin uploaded content")

    def test_upload_overwrites_existing(self):
        """Overwrite works correctly."""
        self._create_file_for_user(self.target_user, "existing.txt", "old content")

        response = self._upload_file_as_admin(
            self.target_user.id, "existing.txt", b"new content"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        file_path = (
            Path(self.test_storage_root)
            / str(self.target_user.account.id)
            / "existing.txt"
        )
        self.assertEqual(file_path.read_text(), "new content")

    def test_upload_creates_parent_dirs(self):
        """Parent directories auto-created."""
        response = self._upload_file_as_admin(
            self.target_user.id, "deep/nested/path/file.txt", b"deep content"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        file_path = (
            Path(self.test_storage_root)
            / str(self.target_user.account.id)
            / "deep/nested/path/file.txt"
        )
        self.assertTrue(file_path.exists())

    def test_non_admin_gets_403(self):
        """Regular user cannot access."""
        regular_user = UserWithProfileFactory(verified=True)
        regular_key = APIKeyFactory(user=regular_user)
        self.authenticate(api_key=regular_key)

        response = self._upload_file_as_admin(self.target_user.id, "file.txt")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_creates_audit_log_with_size(self):
        """Verify action=upload, file_size logged."""
        content = b"audit upload content"
        response = self._upload_file_as_admin(self.target_user.id, "audit.txt", content)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        log = self._assert_audit_log_created(
            action=FileAuditLog.ACTION_UPLOAD,
            path="audit.txt",
            target_user=self.target_user,
        )
        self.assertEqual(log.file_size, len(content))


# =============================================================================
# File Create Tests
# =============================================================================


class AdminFileCreateTest(AdminFileTestMixin, AdminFileTestCase):
    """Tests for POST /api/v1/admin/users/{id}/files/{path}/create/"""

    def setUp(self):
        super().setUp()
        self.target_user = UserWithProfileFactory(verified=True)

    def test_admin_create_empty_file_for_user(self):
        """Admin can create empty file in user's storage."""
        response = self.client.post(
            f"/api/v1/admin/users/{self.target_user.id}/files/newfile.txt/create/"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "newfile.txt")
        self.assertEqual(response.data["size"], 0)
        self.assertIn("detail", response.data)

        # Verify filesystem
        file_path = (
            Path(self.test_storage_root)
            / str(self.target_user.account.id)
            / "newfile.txt"
        )
        self.assertTrue(file_path.exists())
        self.assertEqual(file_path.read_text(), "")

    def test_create_file_in_nested_directory(self):
        """Parent directories auto-created."""
        response = self.client.post(
            f"/api/v1/admin/users/{self.target_user.id}/files/deep/nested/newfile.txt/create/"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        file_path = (
            Path(self.test_storage_root)
            / str(self.target_user.account.id)
            / "deep/nested/newfile.txt"
        )
        self.assertTrue(file_path.exists())

    def test_create_existing_file_returns_409(self):
        """Conflict if file already exists."""
        self._create_file_for_user(self.target_user, "existing.txt", "content")

        response = self.client.post(
            f"/api/v1/admin/users/{self.target_user.id}/files/existing.txt/create/"
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"]["code"], "ALREADY_EXISTS")

    def test_non_admin_gets_403(self):
        """Regular user cannot access."""
        regular_user = UserWithProfileFactory(verified=True)
        regular_key = APIKeyFactory(user=regular_user)
        self.authenticate(api_key=regular_key)

        response = self.client.post(
            f"/api/v1/admin/users/{self.target_user.id}/files/file.txt/create/"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_creates_audit_log_entry(self):
        """Verify action=upload logged for file creation."""
        response = self.client.post(
            f"/api/v1/admin/users/{self.target_user.id}/files/audit.txt/create/"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self._assert_audit_log_created(
            action=FileAuditLog.ACTION_UPLOAD,
            path="audit.txt",
            target_user=self.target_user,
        )

    def test_create_nonexistent_user_returns_404(self):
        """Returns 404 for invalid user_id."""
        response = self.client.post("/api/v1/admin/users/99999/files/file.txt/create/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# =============================================================================
# File Download Tests
# =============================================================================


class AdminFileDownloadTest(AdminFileTestMixin, AdminFileTestCase):
    """Tests for GET /api/v1/admin/users/{id}/files/{path}/download/"""

    def setUp(self):
        super().setUp()
        self.target_user = UserWithProfileFactory(verified=True)

    def test_admin_download_user_file(self):
        """Admin can download user's file."""
        self._create_file_for_user(self.target_user, "download.txt", "download content")

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/files/download.txt/download/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_download_returns_correct_content(self):
        """File content matches."""
        expected_content = "this is the file content"
        self._create_file_for_user(self.target_user, "content.txt", expected_content)

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/files/content.txt/download/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Read streaming content
        content = b"".join(response.streaming_content).decode("utf-8")
        self.assertEqual(content, expected_content)

    def test_download_nonexistent_returns_404(self):
        """Returns 404 for missing file."""
        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/files/nonexistent.txt/download/"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_admin_gets_403(self):
        """Regular user cannot access."""
        self._create_file_for_user(self.target_user, "secret.txt")

        regular_user = UserWithProfileFactory(verified=True)
        regular_key = APIKeyFactory(user=regular_user)
        self.authenticate(api_key=regular_key)

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/files/secret.txt/download/"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_creates_audit_log_entry(self):
        """Verify action=download logged."""
        self._create_file_for_user(self.target_user, "auditdl.txt")

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/files/auditdl.txt/download/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self._assert_audit_log_created(
            action=FileAuditLog.ACTION_DOWNLOAD,
            path="auditdl.txt",
            target_user=self.target_user,
        )


# =============================================================================
# File Delete Tests
# =============================================================================


class AdminFileDeleteTest(AdminFileTestMixin, AdminFileTestCase):
    """Tests for DELETE /api/v1/admin/users/{id}/files/{path}/delete/"""

    def setUp(self):
        super().setUp()
        self.target_user = UserWithProfileFactory(verified=True)

    def test_admin_delete_user_file(self):
        """Admin can delete user's file."""
        self._create_file_for_user(self.target_user, "todelete.txt")
        file_path = (
            Path(self.test_storage_root)
            / str(self.target_user.account.id)
            / "todelete.txt"
        )
        self.assertTrue(file_path.exists())

        response = self.client.delete(
            f"/api/v1/admin/users/{self.target_user.id}/files/todelete.txt/delete/"
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(file_path.exists())
        self.assertFalse(
            StoredFile.objects.filter(
                owner=self.target_user.account, path="todelete.txt"
            ).exists()
        )

    def test_delete_directory_recursive(self):
        """Directory deletion is recursive."""
        self._create_dir_for_user(self.target_user, "deldir")
        self._create_file_for_user(self.target_user, "deldir/file1.txt")
        self._create_file_for_user(self.target_user, "deldir/file2.txt")

        dir_path = (
            Path(self.test_storage_root) / str(self.target_user.account.id) / "deldir"
        )
        self.assertTrue(dir_path.exists())

        response = self.client.delete(
            f"/api/v1/admin/users/{self.target_user.id}/files/deldir/delete/"
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(dir_path.exists())

    def test_delete_nonexistent_returns_404(self):
        """Returns 404 for missing file."""
        response = self.client.delete(
            f"/api/v1/admin/users/{self.target_user.id}/files/ghost.txt/delete/"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_admin_gets_403(self):
        """Regular user cannot access."""
        self._create_file_for_user(self.target_user, "protected.txt")

        regular_user = UserWithProfileFactory(verified=True)
        regular_key = APIKeyFactory(user=regular_user)
        self.authenticate(api_key=regular_key)

        response = self.client.delete(
            f"/api/v1/admin/users/{self.target_user.id}/files/protected.txt/delete/"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_creates_audit_log_entry(self):
        """Verify action=delete logged."""
        self._create_file_for_user(self.target_user, "auditdel.txt")

        response = self.client.delete(
            f"/api/v1/admin/users/{self.target_user.id}/files/auditdel.txt/delete/"
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self._assert_audit_log_created(
            action=FileAuditLog.ACTION_DELETE,
            path="auditdel.txt",
            target_user=self.target_user,
        )


# =============================================================================
# File Content Tests (Preview/Edit)
# =============================================================================


class AdminFileContentTest(AdminFileTestMixin, AdminFileTestCase):
    """Tests for GET/PUT /api/v1/admin/users/{id}/files/{path}/content/"""

    def setUp(self):
        super().setUp()
        self.target_user = UserWithProfileFactory(verified=True)

    def test_admin_preview_user_text_file(self):
        """Admin can preview text file content."""
        self._create_file_for_user(self.target_user, "readme.txt", "Hello World")

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/files/readme.txt/content/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.content.decode("utf-8"), "Hello World")

    def test_admin_edit_user_text_file(self):
        """Admin can edit text file content."""
        self._create_file_for_user(self.target_user, "editable.txt", "original")

        response = self.client.put(
            f"/api/v1/admin/users/{self.target_user.id}/files/editable.txt/content/",
            data="updated content",
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify file was updated
        file_path = (
            Path(self.test_storage_root)
            / str(self.target_user.account.id)
            / "editable.txt"
        )
        self.assertEqual(file_path.read_text(), "updated content")

    def test_preview_binary_returns_400(self):
        """Binary files return NOT_TEXT_FILE error."""
        # Create a binary file
        storage_path = (
            Path(self.test_storage_root)
            / str(self.target_user.account.id)
            / "image.png"
        )
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")

        StoredFile.objects.create(
            owner=self.target_user.account,
            path="image.png",
            name="image.png",
            size=11,
            content_type="image/png",
            is_directory=False,
            parent_path="",
            encryption_method="none",
        )

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/files/image.png/content/"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "NOT_TEXT_FILE")

    def test_non_admin_gets_403(self):
        """Regular user cannot access."""
        self._create_file_for_user(self.target_user, "private.txt")

        regular_user = UserWithProfileFactory(verified=True)
        regular_key = APIKeyFactory(user=regular_user)
        self.authenticate(api_key=regular_key)

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/files/private.txt/content/"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_creates_audit_log_for_preview(self):
        """Verify action=preview logged."""
        self._create_file_for_user(self.target_user, "auditpreview.txt")

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/files/auditpreview.txt/content/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self._assert_audit_log_created(
            action=FileAuditLog.ACTION_PREVIEW,
            path="auditpreview.txt",
            target_user=self.target_user,
        )

    def test_creates_audit_log_for_edit(self):
        """Verify action=edit logged."""
        self._create_file_for_user(self.target_user, "auditedit.txt")

        response = self.client.put(
            f"/api/v1/admin/users/{self.target_user.id}/files/auditedit.txt/content/",
            data="new content",
            content_type="text/plain",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self._assert_audit_log_created(
            action=FileAuditLog.ACTION_EDIT,
            path="auditedit.txt",
            target_user=self.target_user,
        )


# =============================================================================
# File Detail Tests
# =============================================================================


class AdminFileDetailTest(AdminFileTestMixin, AdminFileTestCase):
    """Tests for GET /api/v1/admin/users/{id}/files/{path}/"""

    def setUp(self):
        super().setUp()
        self.target_user = UserWithProfileFactory(verified=True)

    def test_admin_get_file_metadata(self):
        """Admin can get user file metadata."""
        self._create_file_for_user(self.target_user, "metadata.txt", "some content")

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/files/metadata.txt/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "metadata.txt")
        self.assertEqual(response.data["path"], "metadata.txt")

    def test_returns_correct_metadata(self):
        """Size, content_type, dates correct."""
        content = "test content here"
        stored_file = self._create_file_for_user(
            self.target_user, "details.txt", content
        )

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/files/details.txt/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["size"], len(content))
        self.assertEqual(response.data["content_type"], "text/plain")
        self.assertIn("created_at", response.data)
        self.assertIn("modified_at", response.data)

    def test_nonexistent_returns_404(self):
        """Returns 404 for missing file."""
        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/files/missing.txt/"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_admin_gets_403(self):
        """Regular user cannot access."""
        self._create_file_for_user(self.target_user, "info.txt")

        regular_user = UserWithProfileFactory(verified=True)
        regular_key = APIKeyFactory(user=regular_user)
        self.authenticate(api_key=regular_key)

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/files/info.txt/"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# =============================================================================
# Bulk Operation Tests
# =============================================================================


class AdminBulkOperationTest(AdminFileTestMixin, AdminFileTestCase):
    """Tests for POST /api/v1/admin/users/{id}/bulk/"""

    def setUp(self):
        super().setUp()
        self.target_user = UserWithProfileFactory(verified=True)

    def test_admin_bulk_delete_user_files(self):
        """Admin can bulk delete user's files."""
        self._create_file_for_user(self.target_user, "bulk1.txt")
        self._create_file_for_user(self.target_user, "bulk2.txt")

        response = self.client.post(
            f"/api/v1/admin/users/{self.target_user.id}/bulk/",
            {
                "operation": "delete",
                "paths": ["bulk1.txt", "bulk2.txt"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["succeeded"], 2)
        self.assertEqual(response.data["failed"], 0)

    def test_admin_bulk_move_user_files(self):
        """Admin can bulk move user's files."""
        self._create_file_for_user(self.target_user, "move1.txt")
        self._create_file_for_user(self.target_user, "move2.txt")
        self._create_dir_for_user(self.target_user, "dest")

        response = self.client.post(
            f"/api/v1/admin/users/{self.target_user.id}/bulk/",
            {
                "operation": "move",
                "paths": ["move1.txt", "move2.txt"],
                "options": {"destination": "dest"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["succeeded"], 2)

        # Verify files moved
        base = Path(self.test_storage_root) / str(self.target_user.account.id)
        self.assertFalse((base / "move1.txt").exists())
        self.assertTrue((base / "dest" / "move1.txt").exists())

    def test_admin_bulk_copy_user_files(self):
        """Admin can bulk copy user's files."""
        self._create_file_for_user(self.target_user, "copy1.txt")
        self._create_dir_for_user(self.target_user, "backup")

        response = self.client.post(
            f"/api/v1/admin/users/{self.target_user.id}/bulk/",
            {
                "operation": "copy",
                "paths": ["copy1.txt"],
                "options": {"destination": "backup"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["succeeded"], 1)

        # Verify both original and copy exist
        base = Path(self.test_storage_root) / str(self.target_user.account.id)
        self.assertTrue((base / "copy1.txt").exists())
        self.assertTrue((base / "backup" / "copy1.txt").exists())

    def test_non_admin_gets_403(self):
        """Regular user cannot access."""
        self._create_file_for_user(self.target_user, "bulkfile.txt")

        regular_user = UserWithProfileFactory(verified=True)
        regular_key = APIKeyFactory(user=regular_user)
        self.authenticate(api_key=regular_key)

        response = self.client.post(
            f"/api/v1/admin/users/{self.target_user.id}/bulk/",
            {
                "operation": "delete",
                "paths": ["bulkfile.txt"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_creates_audit_log_for_bulk_ops(self):
        """Verify bulk action types logged."""
        self._create_file_for_user(self.target_user, "auditbulk1.txt")
        self._create_file_for_user(self.target_user, "auditbulk2.txt")

        response = self.client.post(
            f"/api/v1/admin/users/{self.target_user.id}/bulk/",
            {
                "operation": "delete",
                "paths": ["auditbulk1.txt", "auditbulk2.txt"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Should have bulk_delete audit log
        log = FileAuditLog.objects.filter(
            action=FileAuditLog.ACTION_BULK_DELETE,
            target_user=self.target_user.account,
        ).first()
        self.assertIsNotNone(log)
        self.assertTrue(log.is_admin_action)
        self.assertEqual(log.performed_by, self.admin.account)


# =============================================================================
# Edge Case Tests
# =============================================================================


class AdminSelfAccessTest(AdminFileTestMixin, AdminFileTestCase):
    """Edge case: Admin accesses their own files via admin endpoint."""

    def test_admin_accessing_own_files_via_admin_endpoint(self):
        """Admin accessing own files via admin endpoint still logs is_admin_action=True."""
        # Create a file for the admin user
        self._create_file_for_user(self.admin, "myfile.txt", "admin's file")

        # Admin accesses their own file via admin endpoint
        response = self.client.get(f"/api/v1/admin/users/{self.admin.id}/dirs/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Even though performed_by == target_user, is_admin_action should be True
        log = FileAuditLog.objects.filter(
            action=FileAuditLog.ACTION_LIST,
            target_user=self.admin.account,
            performed_by=self.admin.account,
        ).first()

        self.assertIsNotNone(log)
        self.assertTrue(
            log.is_admin_action,
            "is_admin_action should be True even when admin accesses own files via admin endpoint",
        )
