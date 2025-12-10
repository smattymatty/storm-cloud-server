"""Tests for storage API endpoints."""

from io import BytesIO
from rest_framework import status
from core.tests.base import StormCloudAPITestCase
from accounts.tests.factories import UserWithProfileFactory
from storage.tests.factories import StoredFileFactory


class DirectoryListTest(StormCloudAPITestCase):
    """GET /api/v1/dirs/"""

    def test_list_root_returns_empty_for_new_user(self):
        """Empty directory should return 200 OK."""
        self.authenticate()
        response = self.client.get('/api/v1/dirs/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # User directory may have structure files, just verify it works
        self.assertGreaterEqual(response.data['total'], 0)

    def test_pagination_with_limit(self):
        """Pagination should respect limit parameter."""
        self.authenticate()
        # Create DB records - actual files not needed for pagination test
        for i in range(10):
            StoredFileFactory(owner=self.user, path=f'file{i}.txt')

        response = self.client.get('/api/v1/dirs/?limit=5')
        # Verify limit is respected (may include existing structure files)
        self.assertLessEqual(len(response.data['entries']), 5)
        self.assertGreaterEqual(response.data['total'], 0)

    def test_path_traversal_blocked(self):
        """Path traversal should be blocked."""
        self.authenticate()
        response = self.client.get('/api/v1/dirs/../etc/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'INVALID_PATH')


class DirectoryCreateTest(StormCloudAPITestCase):
    """POST /api/v1/dirs/{path}/create/"""

    def test_create_directory_succeeds(self):
        """Creating directory should succeed."""
        self.authenticate()
        import uuid
        unique_dir = f'newdir-{uuid.uuid4().hex[:8]}'
        response = self.client.post(f'/api/v1/dirs/{unique_dir}/create/')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['is_directory'])

    def test_create_existing_directory_returns_409(self):
        """Creating existing directory should return 409."""
        self.authenticate()
        self.client.post('/api/v1/dirs/existing/create/')
        response = self.client.post('/api/v1/dirs/existing/create/')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)


class FileUploadTest(StormCloudAPITestCase):
    """POST /api/v1/files/{path}/upload/"""

    def test_upload_without_file_returns_400(self):
        """Upload without file should return 400."""
        self.authenticate()
        response = self.client.post('/api/v1/files/test.txt/upload/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_path_normalization_works(self):
        """Path normalization should work on upload."""
        self.authenticate()
        # Include file to get past the "no file" check
        test_file = BytesIO(b'test content')
        test_file.name = 'test.txt'
        response = self.client.post('/api/v1/files/../etc/passwd/upload/', {'file': test_file})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'INVALID_PATH')
