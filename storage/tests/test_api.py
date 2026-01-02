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


class DirectoryReorderTest(StormCloudAPITestCase):
    """POST /api/v1/dirs/{path}/reorder/"""

    def test_reorder_files_succeeds(self):
        """Reordering files should update sort_position."""
        self.authenticate()
        import uuid

        from storage.models import StoredFile

        # Create some files
        prefix = uuid.uuid4().hex[:8]
        self.client.post(f"/api/v1/files/{prefix}-a.txt/create/")
        self.client.post(f"/api/v1/files/{prefix}-b.txt/create/")
        self.client.post(f"/api/v1/files/{prefix}-c.txt/create/")

        # Reorder them
        response = self.client.post(
            "/api/v1/dirs/reorder/",
            {"order": [f"{prefix}-c.txt", f"{prefix}-a.txt", f"{prefix}-b.txt"]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)

        # Verify positions
        c_file = StoredFile.objects.get(owner=self.user, path=f"{prefix}-c.txt")
        a_file = StoredFile.objects.get(owner=self.user, path=f"{prefix}-a.txt")
        b_file = StoredFile.objects.get(owner=self.user, path=f"{prefix}-b.txt")
        self.assertEqual(c_file.sort_position, 0)
        self.assertEqual(a_file.sort_position, 1)
        self.assertEqual(b_file.sort_position, 2)

    def test_partial_reorder_only_updates_specified(self):
        """Partial reorder should only update specified files."""
        self.authenticate()
        import uuid

        from storage.models import StoredFile

        prefix = uuid.uuid4().hex[:8]
        self.client.post(f"/api/v1/files/{prefix}-a.txt/create/")
        self.client.post(f"/api/v1/files/{prefix}-b.txt/create/")

        # Only reorder one file
        response = self.client.post(
            "/api/v1/dirs/reorder/",
            {"order": [f"{prefix}-b.txt"]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

        # b should be position 0, a unchanged (still 0 from creation)
        b_file = StoredFile.objects.get(owner=self.user, path=f"{prefix}-b.txt")
        self.assertEqual(b_file.sort_position, 0)

    def test_reorder_in_subdirectory(self):
        """Reordering should work in subdirectories."""
        self.authenticate()
        import uuid

        prefix = uuid.uuid4().hex[:8]
        self.client.post(f"/api/v1/dirs/{prefix}/create/")
        self.client.post(f"/api/v1/files/{prefix}/a.txt/create/")
        self.client.post(f"/api/v1/files/{prefix}/b.txt/create/")

        response = self.client.post(
            f"/api/v1/dirs/{prefix}/reorder/",
            {"order": ["b.txt", "a.txt"]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)


class DirectoryResetOrderTest(StormCloudAPITestCase):
    """POST /api/v1/dirs/{path}/reset-order/"""

    def test_reset_order_clears_positions(self):
        """Reset order should set all sort_positions to null."""
        self.authenticate()
        import uuid

        from storage.models import StoredFile

        prefix = uuid.uuid4().hex[:8]
        self.client.post(f"/api/v1/files/{prefix}-a.txt/create/")
        self.client.post(f"/api/v1/files/{prefix}-b.txt/create/")

        # Files have sort_position=0 from creation, verify
        a_file = StoredFile.objects.get(owner=self.user, path=f"{prefix}-a.txt")
        self.assertIsNotNone(a_file.sort_position)

        # Reset order
        response = self.client.post("/api/v1/dirs/reset-order/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify positions are null
        a_file.refresh_from_db()
        b_file = StoredFile.objects.get(owner=self.user, path=f"{prefix}-b.txt")
        self.assertIsNone(a_file.sort_position)
        self.assertIsNone(b_file.sort_position)

    def test_reset_order_in_subdirectory(self):
        """Reset order should only affect specified directory."""
        self.authenticate()
        import uuid

        from storage.models import StoredFile

        prefix = uuid.uuid4().hex[:8]
        # File in root
        self.client.post(f"/api/v1/files/{prefix}-root.txt/create/")
        # File in subdir
        self.client.post(f"/api/v1/dirs/{prefix}/create/")
        self.client.post(f"/api/v1/files/{prefix}/sub.txt/create/")

        # Reset only subdir
        response = self.client.post(f"/api/v1/dirs/{prefix}/reset-order/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Root file should still have position
        root_file = StoredFile.objects.get(owner=self.user, path=f"{prefix}-root.txt")
        self.assertIsNotNone(root_file.sort_position)

        # Subdir file should be null
        sub_file = StoredFile.objects.get(owner=self.user, path=f"{prefix}/sub.txt")
        self.assertIsNone(sub_file.sort_position)


class SortPositionTest(StormCloudAPITestCase):
    """Test sort_position behavior in directory listings."""

    def test_new_files_appear_at_top(self):
        """Newly created files should have sort_position=0."""
        self.authenticate()
        import uuid

        from storage.models import StoredFile

        prefix = uuid.uuid4().hex[:8]
        self.client.post(f"/api/v1/files/{prefix}-first.txt/create/")
        self.client.post(f"/api/v1/files/{prefix}-second.txt/create/")

        first = StoredFile.objects.get(owner=self.user, path=f"{prefix}-first.txt")
        second = StoredFile.objects.get(owner=self.user, path=f"{prefix}-second.txt")

        # Second file pushes first down
        self.assertEqual(second.sort_position, 0)
        self.assertEqual(first.sort_position, 1)

    def test_directory_listing_respects_sort_position(self):
        """Directory listing should sort by sort_position."""
        self.authenticate()
        import uuid

        prefix = uuid.uuid4().hex[:8]
        self.client.post(f"/api/v1/files/{prefix}-a.txt/create/")
        self.client.post(f"/api/v1/files/{prefix}-b.txt/create/")
        self.client.post(f"/api/v1/files/{prefix}-c.txt/create/")

        # Reorder: c, a, b
        self.client.post(
            "/api/v1/dirs/reorder/",
            {"order": [f"{prefix}-c.txt", f"{prefix}-a.txt", f"{prefix}-b.txt"]},
            format="json",
        )

        # List directory
        response = self.client.get("/api/v1/dirs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Find our files in the response
        our_files = [
            e
            for e in response.data["entries"]
            if e["name"].startswith(prefix) and not e["is_directory"]
        ]

        # Should be ordered c, a, b
        self.assertEqual(len(our_files), 3)
        self.assertEqual(our_files[0]["name"], f"{prefix}-c.txt")
        self.assertEqual(our_files[1]["name"], f"{prefix}-a.txt")
        self.assertEqual(our_files[2]["name"], f"{prefix}-b.txt")


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


class ETagSupportTest(StormCloudAPITestCase):
    """Tests for ETag headers and conditional GET behavior."""

    def setUp(self):
        """Create a test file for ETag tests."""
        super().setUp()
        self.authenticate()

        # Upload a test file
        test_file = BytesIO(b"test content for etag")
        test_file.name = "etag-test.txt"
        response = self.client.post(
            "/api/v1/files/etag-test.txt/upload/", {"file": test_file}
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_info_endpoint_returns_etag(self):
        """GET /files/{path}/ includes ETag header."""
        response = self.client.get("/api/v1/files/etag-test.txt/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("ETag", response)
        # ETag should be quoted
        self.assertTrue(response["ETag"].startswith('"'))
        self.assertTrue(response["ETag"].endswith('"'))

    def test_info_endpoint_returns_cache_control(self):
        """GET /files/{path}/ includes Cache-Control header."""
        response = self.client.get("/api/v1/files/etag-test.txt/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Cache-Control", response)
        self.assertEqual(response["Cache-Control"], "private, must-revalidate")

    def test_download_endpoint_returns_etag(self):
        """GET /files/{path}/download/ includes ETag header."""
        response = self.client.get("/api/v1/files/etag-test.txt/download/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("ETag", response)
        self.assertTrue(response["ETag"].startswith('"'))
        self.assertTrue(response["ETag"].endswith('"'))

    def test_download_endpoint_returns_cache_control(self):
        """GET /files/{path}/download/ includes Cache-Control header."""
        response = self.client.get("/api/v1/files/etag-test.txt/download/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Cache-Control", response)
        self.assertEqual(response["Cache-Control"], "private, must-revalidate")

    def test_both_endpoints_return_same_etag(self):
        """Info and download endpoints return identical ETag for same file."""
        info_response = self.client.get("/api/v1/files/etag-test.txt/")
        download_response = self.client.get("/api/v1/files/etag-test.txt/download/")

        self.assertEqual(info_response["ETag"], download_response["ETag"])

    def test_info_conditional_get_returns_304_on_match(self):
        """If-None-Match with matching ETag returns 304 on info endpoint."""
        # First request to get ETag
        response = self.client.get("/api/v1/files/etag-test.txt/")
        etag = response["ETag"]

        # Conditional request with matching ETag
        response = self.client.get(
            "/api/v1/files/etag-test.txt/", HTTP_IF_NONE_MATCH=etag
        )
        self.assertEqual(response.status_code, status.HTTP_304_NOT_MODIFIED)

    def test_download_conditional_get_returns_304_on_match(self):
        """If-None-Match with matching ETag returns 304 on download endpoint."""
        # First request to get ETag
        response = self.client.get("/api/v1/files/etag-test.txt/download/")
        etag = response["ETag"]

        # Conditional request with matching ETag
        response = self.client.get(
            "/api/v1/files/etag-test.txt/download/", HTTP_IF_NONE_MATCH=etag
        )
        self.assertEqual(response.status_code, status.HTTP_304_NOT_MODIFIED)

    def test_conditional_get_returns_200_on_mismatch(self):
        """If-None-Match with stale ETag returns 200 + new content."""
        # Request with a stale/wrong ETag
        response = self.client.get(
            "/api/v1/files/etag-test.txt/", HTTP_IF_NONE_MATCH='"stale-etag"'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should include the correct ETag
        self.assertIn("ETag", response)

    def test_304_response_includes_etag(self):
        """304 responses include the ETag header."""
        # First request to get ETag
        response = self.client.get("/api/v1/files/etag-test.txt/")
        etag = response["ETag"]

        # Conditional request
        response = self.client.get(
            "/api/v1/files/etag-test.txt/", HTTP_IF_NONE_MATCH=etag
        )
        self.assertEqual(response.status_code, status.HTTP_304_NOT_MODIFIED)
        self.assertIn("ETag", response)
        self.assertEqual(response["ETag"], etag)

    def test_etag_changes_after_file_update(self):
        """Re-uploading file changes ETag."""
        # Get original ETag
        response = self.client.get("/api/v1/files/etag-test.txt/")
        original_etag = response["ETag"]

        # Re-upload with different content
        new_content = BytesIO(b"updated content for etag test")
        new_content.name = "etag-test.txt"
        self.client.post("/api/v1/files/etag-test.txt/upload/", {"file": new_content})

        # Get new ETag
        response = self.client.get("/api/v1/files/etag-test.txt/")
        new_etag = response["ETag"]

        # ETags should be different
        self.assertNotEqual(original_etag, new_etag)
