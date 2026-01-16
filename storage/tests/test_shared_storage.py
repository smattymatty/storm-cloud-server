"""Tests for shared organization storage API endpoints."""

import shutil
import uuid
from io import BytesIO

from django.conf import settings
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Organization, Account
from accounts.tests.factories import UserWithAccountFactory, APIKeyFactory
from storage.models import StoredFile


class SharedStorageAPITestCase(APITestCase):
    """
    Base test case for shared storage tests.

    Creates test user with organization and configures isolated storage.
    """

    @classmethod
    def setUpClass(cls):
        """Set up test storage directories."""
        super().setUpClass()
        cls.test_storage_root = settings.BASE_DIR / 'storage_root_test'
        cls.test_shared_root = settings.BASE_DIR / 'shared_storage_test'
        cls.test_storage_root.mkdir(exist_ok=True)
        cls.test_shared_root.mkdir(exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        """Clean up test storage directories."""
        super().tearDownClass()
        if cls.test_storage_root.exists():
            shutil.rmtree(cls.test_storage_root)
        if cls.test_shared_root.exists():
            shutil.rmtree(cls.test_shared_root)

    def setUp(self):
        super().setUp()

        # Create user with organization
        self.user = UserWithAccountFactory(verified=True)
        self.org = self.user.account.organization
        self.api_key = APIKeyFactory(
            organization=self.org,
            created_by=self.user.account,
        )

        # Use test storage roots
        self.settings_override = override_settings(
            STORMCLOUD_STORAGE_ROOT=self.test_storage_root,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.test_shared_root,
            CACHES={
                'default': {
                    'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
                }
            }
        )
        self.settings_override.enable()

    def tearDown(self):
        super().tearDown()
        self.settings_override.disable()

        # Clean up org shared storage
        org_storage = self.test_shared_root / str(self.org.id)
        if org_storage.exists():
            shutil.rmtree(org_storage)

        # Clean up user storage
        user_storage = self.test_storage_root / str(self.user.account.id)
        if user_storage.exists():
            shutil.rmtree(user_storage)

    def authenticate(self):
        """Authenticate requests with API key."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.api_key.key}')


class SharedDirectoryListTest(SharedStorageAPITestCase):
    """GET /api/v1/shared/"""

    def test_list_shared_root_returns_empty_for_new_org(self):
        """Empty shared directory should return 200 OK."""
        self.authenticate()
        response = self.client.get("/api/v1/shared/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["path"], "")

    # NOTE: test_list_shared_requires_organization removed - Account.organization_id
    # is now NOT NULL at database level, so accounts without orgs cannot exist.


class SharedDirectoryCreateTest(SharedStorageAPITestCase):
    """POST /api/v1/shared/dirs/{path}/create/"""

    def test_create_shared_directory_succeeds(self):
        """Creating shared directory should succeed."""
        self.authenticate()
        unique_dir = f"shared-dir-{uuid.uuid4().hex[:8]}"

        response = self.client.post(f"/api/v1/shared/dirs/{unique_dir}/create/")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["is_directory"])
        self.assertEqual(response.data["name"], unique_dir)

        # Verify DB record
        stored = StoredFile.objects.get(organization=self.org, path=unique_dir)
        self.assertTrue(stored.is_directory)
        self.assertIsNone(stored.owner)  # Shared files have no owner

    def test_create_existing_shared_directory_returns_409(self):
        """Creating existing shared directory should return 409."""
        self.authenticate()
        unique_dir = f"existing-{uuid.uuid4().hex[:8]}"

        self.client.post(f"/api/v1/shared/dirs/{unique_dir}/create/")
        response = self.client.post(f"/api/v1/shared/dirs/{unique_dir}/create/")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"]["code"], "ALREADY_EXISTS")

    def test_create_nested_shared_directory_succeeds(self):
        """Creating nested shared directory should succeed."""
        self.authenticate()
        unique_path = f"nested/{uuid.uuid4().hex[:8]}/deep"

        response = self.client.post(f"/api/v1/shared/dirs/{unique_path}/create/")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class SharedFileUploadTest(SharedStorageAPITestCase):
    """POST /api/v1/shared/files/{path}/upload/"""

    def test_upload_shared_file_succeeds(self):
        """Uploading to shared storage should succeed."""
        self.authenticate()
        unique_file = f"shared-file-{uuid.uuid4().hex[:8]}.txt"

        content = b"Hello shared world!"
        response = self.client.post(
            f"/api/v1/shared/files/{unique_file}/upload/",
            {"file": BytesIO(content)},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], unique_file)
        self.assertEqual(response.data["size"], len(content))

        # Verify DB record
        stored = StoredFile.objects.get(organization=self.org, path=unique_file)
        self.assertEqual(stored.size, len(content))
        self.assertIsNone(stored.owner)

    def test_upload_shared_file_in_directory(self):
        """Uploading to shared directory should auto-create parents."""
        self.authenticate()
        unique_path = f"docs/{uuid.uuid4().hex[:8]}/report.txt"

        content = b"Report content"
        response = self.client.post(
            f"/api/v1/shared/files/{unique_path}/upload/",
            {"file": BytesIO(content)},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_upload_without_file_returns_400(self):
        """Upload without file should return 400."""
        self.authenticate()

        response = self.client.post("/api/v1/shared/files/test.txt/upload/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")


class SharedFileDetailTest(SharedStorageAPITestCase):
    """GET /api/v1/shared/files/{path}/"""

    def test_get_shared_file_info(self):
        """Getting shared file info should succeed."""
        self.authenticate()
        unique_file = f"info-test-{uuid.uuid4().hex[:8]}.txt"

        # Upload file first
        content = b"Test content"
        self.client.post(
            f"/api/v1/shared/files/{unique_file}/upload/",
            {"file": BytesIO(content)},
            format="multipart",
        )

        # Get info
        response = self.client.get(f"/api/v1/shared/files/{unique_file}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], unique_file)
        self.assertEqual(response.data["size"], len(content))
        self.assertIn("ETag", response)

    def test_get_nonexistent_shared_file_returns_404(self):
        """Getting nonexistent shared file should return 404."""
        self.authenticate()

        response = self.client.get("/api/v1/shared/files/nonexistent.txt/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "NOT_FOUND")


class SharedFileDownloadTest(SharedStorageAPITestCase):
    """GET /api/v1/shared/files/{path}/download/"""

    def test_download_shared_file_succeeds(self):
        """Downloading shared file should succeed."""
        self.authenticate()
        unique_file = f"download-test-{uuid.uuid4().hex[:8]}.txt"
        content = b"Download me!"

        # Upload file first
        self.client.post(
            f"/api/v1/shared/files/{unique_file}/upload/",
            {"file": BytesIO(content)},
            format="multipart",
        )

        # Download
        response = self.client.get(f"/api/v1/shared/files/{unique_file}/download/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(b"".join(response.streaming_content), content)
        self.assertIn("ETag", response)

    def test_download_with_etag_returns_304(self):
        """Download with matching ETag should return 304 Not Modified."""
        self.authenticate()
        unique_file = f"etag-test-{uuid.uuid4().hex[:8]}.txt"
        content = b"Cached content"

        # Upload file first
        self.client.post(
            f"/api/v1/shared/files/{unique_file}/upload/",
            {"file": BytesIO(content)},
            format="multipart",
        )

        # First download to get ETag
        response1 = self.client.get(f"/api/v1/shared/files/{unique_file}/download/")
        etag = response1["ETag"].strip('"')

        # Second download with ETag
        response2 = self.client.get(
            f"/api/v1/shared/files/{unique_file}/download/",
            HTTP_IF_NONE_MATCH=etag,
        )

        self.assertEqual(response2.status_code, status.HTTP_304_NOT_MODIFIED)


class SharedFileDeleteTest(SharedStorageAPITestCase):
    """DELETE /api/v1/shared/files/{path}/delete/"""

    def test_delete_shared_file_succeeds(self):
        """Deleting shared file should succeed."""
        self.authenticate()
        unique_file = f"delete-test-{uuid.uuid4().hex[:8]}.txt"

        # Upload file first
        self.client.post(
            f"/api/v1/shared/files/{unique_file}/upload/",
            {"file": BytesIO(b"Delete me")},
            format="multipart",
        )

        # Delete
        response = self.client.delete(f"/api/v1/shared/files/{unique_file}/delete/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify deleted from DB
        self.assertFalse(
            StoredFile.objects.filter(organization=self.org, path=unique_file).exists()
        )

    def test_delete_shared_directory_recursive(self):
        """Deleting shared directory should delete contents."""
        self.authenticate()
        dir_name = f"delete-dir-{uuid.uuid4().hex[:8]}"

        # Create directory with files
        self.client.post(f"/api/v1/shared/dirs/{dir_name}/create/")
        self.client.post(
            f"/api/v1/shared/files/{dir_name}/file1.txt/upload/",
            {"file": BytesIO(b"File 1")},
            format="multipart",
        )
        self.client.post(
            f"/api/v1/shared/files/{dir_name}/file2.txt/upload/",
            {"file": BytesIO(b"File 2")},
            format="multipart",
        )

        # Delete directory
        response = self.client.delete(f"/api/v1/shared/files/{dir_name}/delete/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify all deleted from DB
        self.assertFalse(
            StoredFile.objects.filter(
                organization=self.org, path__startswith=dir_name
            ).exists()
        )


class SharedFileContentTest(SharedStorageAPITestCase):
    """GET/PUT /api/v1/shared/files/{path}/content/"""

    def test_preview_shared_text_file(self):
        """Previewing shared text file should return content."""
        self.authenticate()
        unique_file = f"preview-{uuid.uuid4().hex[:8]}.txt"
        content = b"Preview this text content"

        # Upload file
        self.client.post(
            f"/api/v1/shared/files/{unique_file}/upload/",
            {"file": BytesIO(content)},
            format="multipart",
        )

        # Preview
        response = self.client.get(f"/api/v1/shared/files/{unique_file}/content/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.content, content)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")

    def test_edit_shared_text_file(self):
        """Editing shared text file should update content."""
        self.authenticate()
        unique_file = f"edit-{uuid.uuid4().hex[:8]}.txt"

        # Upload file
        self.client.post(
            f"/api/v1/shared/files/{unique_file}/upload/",
            {"file": BytesIO(b"Original content")},
            format="multipart",
        )

        # Edit
        new_content = "Updated shared content"
        response = self.client.put(
            f"/api/v1/shared/files/{unique_file}/content/",
            new_content,
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["size"], len(new_content))

        # Verify content changed
        response2 = self.client.get(f"/api/v1/shared/files/{unique_file}/content/")
        self.assertEqual(response2.content.decode(), new_content)


class SharedStorageQuotaTest(SharedStorageAPITestCase):
    """Test organization quota enforcement for shared storage."""

    def test_upload_exceeds_org_quota(self):
        """Upload exceeding org quota should fail."""
        self.authenticate()

        # Set small org quota (10 bytes)
        self.org.storage_quota_bytes = 10
        self.org.save()

        # Try to upload larger file
        content = b"This content is definitely more than 10 bytes"
        response = self.client.post(
            "/api/v1/shared/files/large.txt/upload/",
            {"file": BytesIO(content)},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_507_INSUFFICIENT_STORAGE)
        self.assertEqual(response.data["error"]["code"], "QUOTA_EXCEEDED")


class SharedStorageIsolationTest(SharedStorageAPITestCase):
    """Test that shared storage is isolated between organizations."""

    def test_cannot_access_other_org_shared_files(self):
        """User cannot access another org's shared files."""
        # Upload file to first org
        self.authenticate()
        unique_file = f"org1-file-{uuid.uuid4().hex[:8]}.txt"
        self.client.post(
            f"/api/v1/shared/files/{unique_file}/upload/",
            {"file": BytesIO(b"Org 1 content")},
            format="multipart",
        )

        # Create second org and user
        org2 = Organization.objects.create(name="Other Org")
        user2 = UserWithAccountFactory(verified=True)
        user2.account.organization = org2
        user2.account.save()
        key2 = APIKeyFactory(organization=org2, created_by=user2.account)

        # Try to access from second org
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {key2.key}')
        response = self.client.get(f"/api/v1/shared/files/{unique_file}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
