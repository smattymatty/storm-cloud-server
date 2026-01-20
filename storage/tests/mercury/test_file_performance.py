"""Performance tests for storage endpoints using Django Mercury."""

import shutil
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import override_settings
from django.utils import timezone
from django_mercury import monitor
from rest_framework.test import APITestCase

from accounts.tests.factories import APIKeyFactory, UserWithProfileFactory
from core.storage.base import FileInfo
from storage.tests.factories import StoredFileFactory


@override_settings(STORAGE_ENCRYPTION_METHOD="none")
class FileOperationPerformance(APITestCase):
    """Performance baselines for file operations."""

    @classmethod
    def setUpClass(cls):
        """Set up test storage directories."""
        super().setUpClass()
        cls.test_storage_root = settings.BASE_DIR / "storage_root_test_mercury_file"
        cls.test_storage_root.mkdir(exist_ok=True)
        cls.test_shared_root = settings.BASE_DIR / "shared_storage_test_mercury_file"
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
        self.user = UserWithProfileFactory(verified=True)
        # Explicitly set created_by so APIKeyUser.account works
        self.api_key = APIKeyFactory(
            organization=self.user.account.organization,
            created_by=self.user.account,
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.api_key.key}")

        # Use test storage roots
        self.settings_override = override_settings(
            STORMCLOUD_STORAGE_ROOT=self.test_storage_root,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.test_shared_root,
        )
        self.settings_override.enable()

        # Create user storage directory
        self.user_storage = self.test_storage_root / str(self.user.account.id)
        self.user_storage.mkdir(exist_ok=True)

    def tearDown(self):
        """Clean up test-specific storage."""
        super().tearDown()
        self.settings_override.disable()

        # Clean up user storage directory
        if self.user_storage.exists():
            shutil.rmtree(self.user_storage)

    @patch("storage.services.LocalStorageBackend")
    def test_directory_listing_under_50ms(self, mock_backend_class):
        """Directory listing with 100 files under 50ms."""
        # Mock backend to return 100 FileInfo objects
        mock_backend = MagicMock()
        mock_backend_class.return_value = mock_backend

        mock_files = [
            FileInfo(
                name=f"file{i}.txt",
                path=f"file{i}.txt",
                size=1024,
                is_directory=False,
                modified_at=timezone.now(),
                content_type="text/plain",
            )
            for i in range(100)
        ]
        mock_backend.list.return_value = mock_files

        with monitor(response_time_ms=50, query_count=3) as result:
            response = self.client.get("/api/v1/user/dirs/?limit=100")
        result.explain()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["entries"]), 100)

    def test_file_upload_1mb_under_50ms(self):
        """1MB upload under 50ms."""
        content = BytesIO(b"x" * (1024 * 1024))
        content.name = "test.bin"

        # Create parent directory first
        self.client.post("/api/v1/user/dirs/uploads/create/")

        with monitor(response_time_ms=50, query_count=14) as result:
            response = self.client.post(
                "/api/v1/user/files/uploads/test.bin/upload/",
                {"file": content},
                format="multipart",
            )
        result.explain()

        self.assertEqual(response.status_code, 201)


@override_settings(STORAGE_ENCRYPTION_METHOD="none")
class DirectoryListingScaleTest(APITestCase):
    """Test directory listing with many files."""

    @classmethod
    def setUpClass(cls):
        """Set up test storage directories."""
        super().setUpClass()
        cls.test_storage_root = settings.BASE_DIR / "storage_root_test_mercury_scale"
        cls.test_storage_root.mkdir(exist_ok=True)
        cls.test_shared_root = settings.BASE_DIR / "shared_storage_test_mercury_scale"
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
        self.user = UserWithProfileFactory(verified=True)
        # Explicitly set created_by so APIKeyUser.account works
        self.api_key = APIKeyFactory(
            organization=self.user.account.organization,
            created_by=self.user.account,
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.api_key.key}")

        # Use test storage roots
        self.settings_override = override_settings(
            STORMCLOUD_STORAGE_ROOT=self.test_storage_root,
            STORMCLOUD_SHARED_STORAGE_ROOT=self.test_shared_root,
        )
        self.settings_override.enable()

        # Create 100 file records
        for i in range(100):
            StoredFileFactory(owner=self.user.account, path=f"file{i}.txt")

    def tearDown(self):
        """Clean up."""
        super().tearDown()
        self.settings_override.disable()

    def test_list_100_files_under_500ms_no_n1(self):
        """Listing 100 files should be efficient."""
        with monitor(response_time_ms=500, query_count=20) as result:
            response = self.client.get("/api/v1/user/dirs/")

        self.assertEqual(response.status_code, 200)
