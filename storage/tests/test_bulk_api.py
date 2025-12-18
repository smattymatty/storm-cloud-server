"""Tests for Bulk Operations API endpoints."""

import shutil
from pathlib import Path
from django.test import TestCase, override_settings
from django.conf import settings
from rest_framework.test import APIClient
from rest_framework import status

from accounts.tests.factories import UserWithProfileFactory
from storage.models import StoredFile


class BulkOperationAPITestCase(TestCase):
    """Test suite for bulk operations API."""

    @classmethod
    def setUpClass(cls):
        """Set up test storage directory."""
        super().setUpClass()
        cls.test_storage_root = settings.BASE_DIR / 'storage_root_test_bulk_api'
        cls.test_storage_root.mkdir(exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        """Clean up test storage directory."""
        super().tearDownClass()
        if cls.test_storage_root.exists():
            shutil.rmtree(cls.test_storage_root)

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        self.user = UserWithProfileFactory(verified=True)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        
        # Use test storage root
        self.settings_override = override_settings(
            STORMCLOUD_STORAGE_ROOT=self.test_storage_root,
        )
        self.settings_override.enable()
        
        # Create user storage directory
        self.user_storage = self.test_storage_root / str(self.user.id)
        self.user_storage.mkdir(exist_ok=True)

    def tearDown(self):
        """Clean up test-specific storage."""
        super().tearDown()
        self.settings_override.disable()
        
        # Clean up user storage directory
        if self.user_storage.exists():
            shutil.rmtree(self.user_storage)

    def _create_file(self, path: str, content: str = "test") -> None:
        """Helper to create a file on disk and in DB."""
        file_path = self.user_storage / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        
        parent_path = str(Path(path).parent) if "/" in path else ""
        if parent_path == ".":
            parent_path = ""
            
        StoredFile.objects.create(
            owner=self.user,
            path=path,
            name=Path(path).name,
            size=len(content),
            content_type='text/plain',
            is_directory=False,
            parent_path=parent_path,
            encryption_method='none'
        )

    def _create_directory(self, path: str) -> None:
        """Helper to create a directory on disk and in DB."""
        dir_path = self.user_storage / path
        dir_path.mkdir(parents=True, exist_ok=True)
        
        parent_path = str(Path(path).parent) if "/" in path else ""
        if parent_path == ".":
            parent_path = ""
            
        StoredFile.objects.create(
            owner=self.user,
            path=path,
            name=Path(path).name,
            size=0,
            content_type='',
            is_directory=True,
            parent_path=parent_path,
            encryption_method='none'
        )

    # =========================================================================
    # Authentication & Authorization Tests
    # =========================================================================

    def test_requires_authentication(self):
        """Test that bulk operations require authentication."""
        client = APIClient()  # Unauthenticated
        
        response = client.post('/api/v1/bulk/', {
            'operation': 'delete',
            'paths': ['test.txt']
        }, format='json')
        
        # DRF returns 403 for unauthenticated requests by default
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    # =========================================================================
    # Validation Tests
    # =========================================================================

    def test_missing_operation_field(self):
        """Test that operation field is required."""
        response = self.client.post('/api/v1/bulk/', {
            'paths': ['test.txt']
        })
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_missing_paths_field(self):
        """Test that paths field is required."""
        response = self.client.post('/api/v1/bulk/', {
            'operation': 'delete'
        })
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_operation(self):
        """Test that invalid operations are rejected."""
        response = self.client.post('/api/v1/bulk/', {
            'operation': 'invalid',
            'paths': ['test.txt']
        })
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_paths_array(self):
        """Test that empty paths array is rejected."""
        response = self.client.post('/api/v1/bulk/', {
            'operation': 'delete',
            'paths': []
        })
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_too_many_paths(self):
        """Test that >250 paths is rejected."""
        paths = [f'file{i}.txt' for i in range(251)]
        
        response = self.client.post('/api/v1/bulk/', {
            'operation': 'delete',
            'paths': paths
        })
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_move_requires_destination(self):
        """Test that move operation requires destination in options."""
        response = self.client.post('/api/v1/bulk/', {
            'operation': 'move',
            'paths': ['test.txt']
        })
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # =========================================================================
    # Delete Operation Tests
    # =========================================================================

    def test_delete_operation(self):
        """Test delete operation via API."""
        self._create_file('file1.txt')
        self._create_file('file2.txt')
        
        response = self.client.post('/api/v1/bulk/', {
            'operation': 'delete',
            'paths': ['file1.txt', 'file2.txt']
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['operation'], 'delete')
        self.assertEqual(response.data['total'], 2)
        self.assertEqual(response.data['succeeded'], 2)
        self.assertEqual(response.data['failed'], 0)
        
        # Verify files deleted
        self.assertEqual(StoredFile.objects.filter(owner=self.user).count(), 0)

    def test_delete_partial_failure(self):
        """Test delete with mix of existing and missing files."""
        self._create_file('exists.txt')
        
        response = self.client.post('/api/v1/bulk/', {
            'operation': 'delete',
            'paths': ['exists.txt', 'missing.txt']
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['succeeded'], 1)
        self.assertEqual(response.data['failed'], 1)

    # =========================================================================
    # Move Operation Tests
    # =========================================================================

    def test_move_operation(self):
        """Test move operation via API."""
        self._create_file('source.txt')
        self._create_directory('dest')
        
        response = self.client.post('/api/v1/bulk/', {
            'operation': 'move',
            'paths': ['source.txt'],
            'options': {'destination': 'dest'}
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['succeeded'], 1)
        self.assertEqual(response.data['results'][0]['data']['new_path'], 'dest/source.txt')
        
        # Verify file moved
        self.assertTrue((self.user_storage / 'dest' / 'source.txt').exists())
        self.assertFalse((self.user_storage / 'source.txt').exists())

    # =========================================================================
    # Copy Operation Tests
    # =========================================================================

    def test_copy_operation(self):
        """Test copy operation via API."""
        self._create_file('source.txt', 'content')
        self._create_directory('dest')
        
        response = self.client.post('/api/v1/bulk/', {
            'operation': 'copy',
            'paths': ['source.txt'],
            'options': {'destination': 'dest'}
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['succeeded'], 1)
        
        # Verify both files exist
        self.assertTrue((self.user_storage / 'source.txt').exists())
        self.assertTrue((self.user_storage / 'dest' / 'source.txt').exists())

    # =========================================================================
    # Response Format Tests
    # =========================================================================

    def test_sync_response_format(self):
        """Test that sync operations return correct response format."""
        self._create_file('test.txt')
        
        response = self.client.post('/api/v1/bulk/', {
            'operation': 'delete',
            'paths': ['test.txt']
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify response structure
        self.assertIn('operation', response.data)
        self.assertIn('total', response.data)
        self.assertIn('succeeded', response.data)
        self.assertIn('failed', response.data)
        self.assertIn('results', response.data)
        
        # Verify results structure
        result = response.data['results'][0]
        self.assertIn('path', result)
        self.assertIn('success', result)

    def test_async_response_format_fallback(self):
        """Test large batch response (with async fallback when Tasks unavailable)."""
        # Create 51 files to trigger async threshold
        for i in range(51):
            self._create_file(f'file{i}.txt')
        
        paths = [f'file{i}.txt' for i in range(51)]
        
        response = self.client.post('/api/v1/bulk/', {
            'operation': 'delete',
            'paths': paths
        })
        
        # Could be 200 (fallback) or 202 (async) depending on Django Tasks availability
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_202_ACCEPTED])
        
        if response.status_code == status.HTTP_202_ACCEPTED:
            # Async response
            self.assertIn('task_id', response.data)
            self.assertIn('total', response.data)
        else:
            # Fallback to sync
            self.assertEqual(response.data['total'], 51)
