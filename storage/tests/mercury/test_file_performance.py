"""Performance tests for storage endpoints using Django Mercury."""

from io import BytesIO
from unittest.mock import patch, MagicMock
from rest_framework.test import APITestCase
from django_mercury import monitor
from accounts.tests.factories import UserWithProfileFactory, APIKeyFactory
from storage.tests.factories import StoredFileFactory
from core.storage.base import FileInfo


class FileOperationPerformance(APITestCase):
    """Performance baselines for file operations."""

    def setUp(self):
        super().setUp()
        self.user = UserWithProfileFactory(verified=True)
        self.api_key = APIKeyFactory(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.api_key.key}')

    @patch('storage.api.LocalStorageBackend')
    def test_directory_listing_under_50ms(self, mock_backend_class):
        """Directory listing with 100 files under 50ms."""
        # Mock backend to return 100 FileInfo objects
        mock_backend = MagicMock()
        mock_backend_class.return_value = mock_backend

        mock_files = [
            FileInfo(
                name=f'file{i}.txt',
                path=f'file{i}.txt',
                size=1024,
                is_directory=False,
                modified_at=None,
                content_type='text/plain'
            )
            for i in range(100)
        ]
        mock_backend.list.return_value = mock_files

        with monitor(response_time_ms=50, query_count=2) as result:
            response = self.client.get('/api/v1/dirs/?limit=100')
        result.explain()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['entries']), 100)

    def test_file_upload_1mb_under_50ms(self):
        """1MB upload under 50ms."""
        content = BytesIO(b'x' * (1024 * 1024))
        content.name = 'test.bin'

        # Create parent directory first
        self.client.post('/api/v1/dirs/uploads/create/')

        with monitor(response_time_ms=50, query_count=8) as result:
            response = self.client.post(
                '/api/v1/files/uploads/test.bin/upload/',
                {'file': content},
                format='multipart'
            )
        result.explain()

        self.assertEqual(response.status_code, 201)


class DirectoryListingScaleTest(APITestCase):
    """Test directory listing with many files."""

    def setUp(self):
        super().setUp()
        self.user = UserWithProfileFactory(verified=True)
        self.api_key = APIKeyFactory(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.api_key.key}')

        # Create 100 file records
        for i in range(100):
            StoredFileFactory(owner=self.user, path=f'file{i}.txt')

    def test_list_100_files_under_500ms_no_n1(self):
        """Listing 100 files should be efficient."""
        with monitor(response_time_ms=500, query_count=20) as result:
            response = self.client.get('/api/v1/dirs/')

        self.assertEqual(response.status_code, 200)
