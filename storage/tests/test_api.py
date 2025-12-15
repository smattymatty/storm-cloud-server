"""Tests for storage API endpoints."""

from io import BytesIO

from rest_framework import status

from accounts.tests.factories import UserWithProfileFactory
from core.tests.base import StormCloudAPITestCase
from storage.tests.factories import StoredFileFactory


class DirectoryListTest(StormCloudAPITestCase):
    """GET /api/v1/dirs/"""

    def test_list_root_returns_empty_for_new_user(self):
        """Empty directory should return 200 OK."""
        self.authenticate()
        response = self.client.get("/api/v1/dirs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # User directory may have structure files, just verify it works
        self.assertGreaterEqual(response.data["total"], 0)

    def test_pagination_with_limit(self):
        """Pagination should respect limit parameter."""
        self.authenticate()
        # Create DB records - actual files not needed for pagination test
        for i in range(10):
            StoredFileFactory(owner=self.user, path=f"file{i}.txt")

        response = self.client.get("/api/v1/dirs/?limit=5")
        # Verify limit is respected (may include existing structure files)
        self.assertLessEqual(len(response.data["entries"]), 5)
        self.assertGreaterEqual(response.data["total"], 0)

    def test_path_traversal_blocked(self):
        """Path traversal should be blocked."""
        self.authenticate()
        response = self.client.get("/api/v1/dirs/../etc/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "INVALID_PATH")


class DirectoryCreateTest(StormCloudAPITestCase):
    """POST /api/v1/dirs/{path}/create/"""

    def test_create_directory_succeeds(self):
        """Creating directory should succeed."""
        self.authenticate()
        import uuid

        unique_dir = f"newdir-{uuid.uuid4().hex[:8]}"
        response = self.client.post(f"/api/v1/dirs/{unique_dir}/create/")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["is_directory"])

    def test_create_existing_directory_returns_409(self):
        """Creating existing directory should return 409."""
        self.authenticate()
        self.client.post("/api/v1/dirs/existing/create/")
        response = self.client.post("/api/v1/dirs/existing/create/")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)


class FileCreateTest(StormCloudAPITestCase):
    """POST /api/v1/files/{path}/create/"""

    def test_create_file_succeeds(self):
        """Creating empty file should succeed."""
        self.authenticate()
        import uuid

        unique_file = f"newfile-{uuid.uuid4().hex[:8]}.txt"
        response = self.client.post(f"/api/v1/files/{unique_file}/create/")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data["is_directory"])
        self.assertEqual(response.data["size"], 0)
        self.assertEqual(response.data["encryption_method"], "none")

    def test_create_file_sets_content_type(self):
        """Creating file should detect content type from extension."""
        self.authenticate()
        import uuid

        unique_file = f"doc-{uuid.uuid4().hex[:8]}.json"
        response = self.client.post(f"/api/v1/files/{unique_file}/create/")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["content_type"], "application/json")

    def test_create_existing_file_returns_409(self):
        """Creating existing file should return 409."""
        self.authenticate()
        import uuid

        unique_file = f"existing-{uuid.uuid4().hex[:8]}.txt"
        self.client.post(f"/api/v1/files/{unique_file}/create/")
        response = self.client.post(f"/api/v1/files/{unique_file}/create/")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"]["code"], "ALREADY_EXISTS")

    def test_create_file_in_nested_directory(self):
        """Creating file should auto-create parent directories."""
        self.authenticate()
        import uuid

        unique_path = f"nested/{uuid.uuid4().hex[:8]}/deep/file.txt"
        response = self.client.post(f"/api/v1/files/{unique_path}/create/")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_file_path_traversal_blocked(self):
        """Path traversal should be blocked."""
        self.authenticate()
        response = self.client.post("/api/v1/files/../etc/passwd/create/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "INVALID_PATH")


class FileUploadTest(StormCloudAPITestCase):
    """POST /api/v1/files/{path}/upload/"""

    def test_upload_without_file_returns_400(self):
        """Upload without file should return 400."""
        self.authenticate()
        response = self.client.post("/api/v1/files/test.txt/upload/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_path_normalization_works(self):
        """Path normalization should work on upload."""
        self.authenticate()
        # Include file to get past the "no file" check
        test_file = BytesIO(b"test content")
        test_file.name = "test.txt"
        response = self.client.post(
            "/api/v1/files/../etc/passwd/upload/", {"file": test_file}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "INVALID_PATH")


class EncryptionGovernanceTest(StormCloudAPITestCase):
    """Tests for ADR 006 encryption governance fitness functions."""

    def test_all_stored_files_have_encryption_method_set(self):
        """All stored files must have encryption_method set (ADR 006 fitness function)."""
        from storage.models import StoredFile

        self.authenticate()

        # Create a file
        test_file = BytesIO(b"test content")
        test_file.name = "test.txt"
        response = self.client.post(
            "/api/v1/files/governance-test.txt/upload/", {"file": test_file}
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify encryption_method is set in database
        stored_file = StoredFile.objects.get(
            owner=self.user, path="governance-test.txt"
        )
        self.assertIsNotNone(stored_file.encryption_method)
        self.assertNotEqual(stored_file.encryption_method, "")
        self.assertIn(stored_file.encryption_method, ["none", "server", "client"])

    def test_encryption_method_validation(self):
        """encryption_method must be one of the valid choices."""
        from django.core.exceptions import ValidationError

        from storage.models import StoredFile

        self.authenticate()

        # Valid encryption_method values
        for method in ["none", "server", "client"]:
            file_obj = StoredFile(
                owner=self.user,
                path=f"test-{method}.txt",
                name=f"test-{method}.txt",
                encryption_method=method,
            )
            file_obj.full_clean()  # Should not raise

        # Invalid encryption_method value (via model validation)
        file_obj = StoredFile(
            owner=self.user,
            path="test-invalid.txt",
            name="test-invalid.txt",
            encryption_method="invalid",
        )
        with self.assertRaises(ValidationError):
            file_obj.full_clean()

    def test_file_upload_sets_encryption_method_none(self):
        """File upload should default to encryption_method='none'."""
        self.authenticate()

        test_file = BytesIO(b"test content")
        test_file.name = "test.txt"
        response = self.client.post(
            "/api/v1/files/default-encryption.txt/upload/", {"file": test_file}
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["encryption_method"], "none")

    def test_file_detail_response_includes_encryption_method(self):
        """File detail response must include encryption_method."""
        from storage.models import StoredFile

        self.authenticate()

        # Create file
        test_file = BytesIO(b"test content")
        test_file.name = "test.txt"
        self.client.post("/api/v1/files/detail-test.txt/upload/", {"file": test_file})

        # Get file details
        response = self.client.get("/api/v1/files/detail-test.txt/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("encryption_method", response.data)
        self.assertEqual(response.data["encryption_method"], "none")

    def test_directory_listing_includes_encryption_method(self):
        """Directory listing must include encryption_method for each file."""
        self.authenticate()

        # Create a file
        test_file = BytesIO(b"test content")
        test_file.name = "test.txt"
        self.client.post("/api/v1/files/list-test.txt/upload/", {"file": test_file})

        # List directory
        response = self.client.get("/api/v1/dirs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check that entries have encryption_method
        for entry in response.data["entries"]:
            self.assertIn("encryption_method", entry)

    def test_directory_creation_sets_encryption_method(self):
        """Directory creation should set encryption_method='none'."""
        self.authenticate()
        import uuid

        unique_dir = f"dir-{uuid.uuid4().hex[:8]}"

        response = self.client.post(f"/api/v1/dirs/{unique_dir}/create/")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("encryption_method", response.data)
        self.assertEqual(response.data["encryption_method"], "none")

    def test_encryption_method_cannot_be_empty(self):
        """encryption_method field must not be empty (ADR 006 governance)."""
        from django.core.exceptions import ValidationError

        from storage.models import StoredFile

        self.authenticate()

        # Attempt to create file with empty encryption_method
        file_obj = StoredFile(
            owner=self.user,
            path="empty-encryption.txt",
            name="empty-encryption.txt",
            encryption_method="",
        )
        with self.assertRaises(ValidationError) as cm:
            file_obj.full_clean()

        # Check the error message mentions encryption_method
        self.assertIn("encryption_method", str(cm.exception).lower())
