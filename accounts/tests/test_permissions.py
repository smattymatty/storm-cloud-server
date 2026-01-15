"""Tests for user permission flags."""

from rest_framework import status

from core.tests.base import StormCloudAPITestCase
from accounts.tests.factories import UserWithProfileFactory, APIKeyFactory


class PermissionUploadTest(StormCloudAPITestCase):
    """Tests for can_upload permission."""

    def test_upload_denied_when_can_upload_false(self):
        """User with can_upload=False cannot upload files."""
        self.authenticate()
        self.user.account.can_upload = False
        self.user.account.save()

        with open(__file__, 'rb') as f:
            response = self.client.post(
                '/api/v1/files/test.txt/upload/',
                {'file': f},
                format='multipart'
            )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error']['code'], 'PERMISSION_DENIED')
        self.assertEqual(response.data['error']['permission'], 'can_upload')

    def test_upload_allowed_when_can_upload_true(self):
        """User with can_upload=True can upload files."""
        self.authenticate()
        # Default is True, but let's be explicit
        self.user.account.can_upload = True
        self.user.account.save()

        with open(__file__, 'rb') as f:
            response = self.client.post(
                '/api/v1/files/test.txt/upload/',
                {'file': f},
                format='multipart'
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class PermissionDeleteTest(StormCloudAPITestCase):
    """Tests for can_delete permission."""

    def test_delete_denied_when_can_delete_false(self):
        """User with can_delete=False cannot delete files."""
        self.authenticate()

        # First upload a file
        with open(__file__, 'rb') as f:
            self.client.post(
                '/api/v1/files/deleteme.txt/upload/',
                {'file': f},
                format='multipart'
            )

        # Now disable delete permission
        self.user.account.can_delete = False
        self.user.account.save()

        response = self.client.delete('/api/v1/files/deleteme.txt/delete/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error']['code'], 'PERMISSION_DENIED')
        self.assertEqual(response.data['error']['permission'], 'can_delete')

    def test_delete_allowed_when_can_delete_true(self):
        """User with can_delete=True can delete files."""
        self.authenticate()

        # First upload a file
        with open(__file__, 'rb') as f:
            self.client.post(
                '/api/v1/files/deleteme.txt/upload/',
                {'file': f},
                format='multipart'
            )

        response = self.client.delete('/api/v1/files/deleteme.txt/delete/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class PermissionOverwriteTest(StormCloudAPITestCase):
    """Tests for can_overwrite permission."""

    def test_overwrite_denied_when_can_overwrite_false(self):
        """User with can_overwrite=False cannot overwrite files."""
        self.authenticate()

        # First upload a file
        with open(__file__, 'rb') as f:
            self.client.post(
                '/api/v1/files/overwrite.txt/upload/',
                {'file': f},
                format='multipart'
            )

        # Now disable overwrite permission
        self.user.account.can_overwrite = False
        self.user.account.save()

        # Try to overwrite
        with open(__file__, 'rb') as f:
            response = self.client.post(
                '/api/v1/files/overwrite.txt/upload/',
                {'file': f},
                format='multipart'
            )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error']['code'], 'PERMISSION_DENIED')
        self.assertEqual(response.data['error']['permission'], 'can_overwrite')

    def test_content_edit_denied_when_can_overwrite_false(self):
        """User with can_overwrite=False cannot edit file content."""
        self.authenticate()

        # First upload a file
        with open(__file__, 'rb') as f:
            self.client.post(
                '/api/v1/files/edit.txt/upload/',
                {'file': f},
                format='multipart'
            )

        # Now disable overwrite permission
        self.user.account.can_overwrite = False
        self.user.account.save()

        # Try to edit content
        response = self.client.put(
            '/api/v1/files/edit.txt/content/',
            'new content',
            content_type='text/plain'
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error']['code'], 'PERMISSION_DENIED')
        self.assertEqual(response.data['error']['permission'], 'can_overwrite')


class PermissionShareTest(StormCloudAPITestCase):
    """Tests for can_create_shares and max_share_links permissions."""

    def test_share_denied_when_can_create_shares_false(self):
        """User with can_create_shares=False cannot create share links."""
        self.authenticate()

        # First upload a file
        with open(__file__, 'rb') as f:
            self.client.post(
                '/api/v1/files/share.txt/upload/',
                {'file': f},
                format='multipart'
            )

        # Now disable share permission
        self.user.account.can_create_shares = False
        self.user.account.save()

        response = self.client.post('/api/v1/shares/', {'file_path': 'share.txt'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error']['code'], 'PERMISSION_DENIED')
        self.assertEqual(response.data['error']['permission'], 'can_create_shares')

    def test_share_denied_when_max_share_links_exceeded(self):
        """User cannot create more share links than max_share_links allows."""
        self.authenticate()

        # Upload files
        for i in range(3):
            with open(__file__, 'rb') as f:
                self.client.post(
                    f'/api/v1/files/share{i}.txt/upload/',
                    {'file': f},
                    format='multipart'
                )

        # Set max share links to 2
        self.user.account.max_share_links = 2
        self.user.account.save()

        # Create 2 shares (should work)
        self.client.post('/api/v1/shares/', {'file_path': 'share0.txt'})
        self.client.post('/api/v1/shares/', {'file_path': 'share1.txt'})

        # Third should fail
        response = self.client.post('/api/v1/shares/', {'file_path': 'share2.txt'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error']['code'], 'MAX_SHARE_LINKS_EXCEEDED')


class PermissionBulkTest(StormCloudAPITestCase):
    """Tests for bulk operation permissions."""

    def test_bulk_delete_denied_when_can_delete_false(self):
        """User with can_delete=False cannot bulk delete."""
        self.authenticate()

        # Upload a file
        with open(__file__, 'rb') as f:
            self.client.post(
                '/api/v1/files/bulk1.txt/upload/',
                {'file': f},
                format='multipart'
            )

        # Disable delete permission
        self.user.account.can_delete = False
        self.user.account.save()

        response = self.client.post('/api/v1/bulk/', {
            'operation': 'delete',
            'paths': ['bulk1.txt']
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error']['code'], 'PERMISSION_DENIED')
        self.assertEqual(response.data['error']['permission'], 'can_delete')

    def test_bulk_move_denied_when_can_move_false(self):
        """User with can_move=False cannot bulk move."""
        self.authenticate()

        # Upload a file and create destination folder
        with open(__file__, 'rb') as f:
            self.client.post(
                '/api/v1/files/moveme.txt/upload/',
                {'file': f},
                format='multipart'
            )
        self.client.post('/api/v1/dirs/', {'path': 'dest'}, format='json')

        # Disable move permission
        self.user.account.can_move = False
        self.user.account.save()

        response = self.client.post('/api/v1/bulk/', {
            'operation': 'move',
            'paths': ['moveme.txt'],
            'options': {'destination': 'dest'}
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error']['code'], 'PERMISSION_DENIED')
        self.assertEqual(response.data['error']['permission'], 'can_move')

    def test_bulk_copy_denied_when_can_upload_false(self):
        """User with can_upload=False cannot bulk copy (creates new files)."""
        self.authenticate()

        # Upload a file and create destination folder
        with open(__file__, 'rb') as f:
            self.client.post(
                '/api/v1/files/copyme.txt/upload/',
                {'file': f},
                format='multipart'
            )
        self.client.post('/api/v1/dirs/', {'path': 'dest'}, format='json')

        # Disable upload permission
        self.user.account.can_upload = False
        self.user.account.save()

        response = self.client.post('/api/v1/bulk/', {
            'operation': 'copy',
            'paths': ['copyme.txt'],
            'options': {'destination': 'dest'}
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error']['code'], 'PERMISSION_DENIED')
        self.assertEqual(response.data['error']['permission'], 'can_upload')


class AdminPermissionsUpdateTest(StormCloudAPITestCase):
    """Tests for admin permissions update endpoint."""

    def test_admin_can_update_user_permissions(self):
        """Admin can update user permission flags."""
        # Create admin and target user
        admin = UserWithProfileFactory(admin=True)
        admin_key = APIKeyFactory(
            organization=admin.account.organization,
            created_by=admin.account,
        )
        target_user = UserWithProfileFactory(verified=True)

        self.authenticate(api_key=admin_key)

        response = self.client.patch(
            f'/api/v1/admin/users/{target_user.id}/permissions/',
            {
                'can_upload': False,
                'can_delete': False,
                'max_share_links': 5
            },
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['permissions']['can_upload'], False)
        self.assertEqual(response.data['permissions']['can_delete'], False)
        self.assertEqual(response.data['permissions']['max_share_links'], 5)

        # Verify in database
        target_user.account.refresh_from_db()
        self.assertFalse(target_user.account.can_upload)
        self.assertFalse(target_user.account.can_delete)
        self.assertEqual(target_user.account.max_share_links, 5)

    def test_non_admin_cannot_update_permissions(self):
        """Non-admin users cannot update permissions."""
        self.authenticate()
        target_user = UserWithProfileFactory(verified=True)

        response = self.client.patch(
            f'/api/v1/admin/users/{target_user.id}/permissions/',
            {'can_upload': False},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_partial_update_only_changes_specified_fields(self):
        """PATCH only updates the fields that are provided."""
        admin = UserWithProfileFactory(admin=True)
        admin_key = APIKeyFactory(
            organization=admin.account.organization,
            created_by=admin.account,
        )
        target_user = UserWithProfileFactory(verified=True)

        # Set initial values - ensure both are True
        target_user.account.can_upload = True
        target_user.account.can_delete = True
        target_user.account.save(update_fields=['can_upload', 'can_delete'])

        self.authenticate(api_key=admin_key)

        # Only update can_upload
        response = self.client.patch(
            f'/api/v1/admin/users/{target_user.id}/permissions/',
            {'can_upload': False},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check the response directly - it should show can_delete unchanged
        self.assertFalse(response.data['permissions']['can_upload'])
        self.assertTrue(response.data['permissions']['can_delete'])  # Should remain True


class AdminUserDetailPermissionsTest(StormCloudAPITestCase):
    """Tests that admin user detail includes permissions."""

    def test_admin_user_detail_includes_permissions(self):
        """Admin user detail response includes permission fields."""
        admin = UserWithProfileFactory(admin=True)
        admin_key = APIKeyFactory(
            organization=admin.account.organization,
            created_by=admin.account,
        )
        target_user = UserWithProfileFactory(verified=True)

        # Set some specific permission values
        target_user.account.can_upload = False
        target_user.account.max_share_links = 10
        target_user.account.save()

        self.authenticate(api_key=admin_key)

        response = self.client.get(f'/api/v1/admin/users/{target_user.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile = response.data['profile']
        self.assertIn('can_upload', profile)
        self.assertIn('can_delete', profile)
        self.assertIn('can_move', profile)
        self.assertIn('can_overwrite', profile)
        self.assertIn('can_create_shares', profile)
        self.assertIn('max_share_links', profile)
        self.assertIn('max_upload_bytes', profile)
        self.assertEqual(profile['can_upload'], False)
        self.assertEqual(profile['max_share_links'], 10)
