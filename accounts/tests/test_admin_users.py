"""Tests for admin user management endpoints."""

from django.contrib.auth import get_user_model
from rest_framework import status

from core.tests.base import StormCloudAdminTestCase, StormCloudAPITestCase
from accounts.tests.factories import UserWithProfileFactory

User = get_user_model()


class AdminUserCreateTest(StormCloudAdminTestCase):
    """Tests for POST /api/v1/admin/users/create/"""

    def test_admin_create_user_succeeds(self):
        """Admin can create user with custom settings."""
        # with username, email, password, is_email_verified, is_staff
        # assert response.status_code == 201
        # Verify user was created with correct attributes
        data = {
            'username': 'newadminuser',
            'email': 'newadmin@example.com',
            'password': 'testpass123',
            'is_email_verified': True,
            'is_staff': True,
        }
        response = self.client.post('/api/v1/admin/users/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(username='newadminuser')
        self.assertTrue(user.is_staff)
        self.assertTrue(user.profile.is_email_verified)

    def test_admin_create_user_bypasses_registration_setting(self):
        """Admin can create users even when ALLOW_REGISTRATION=False."""
        # POST create user
        # assert response.status_code == 201
        data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'testpass123',
        }
        response = self.client.post('/api/v1/admin/users/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_non_admin_cannot_create_user(self):
        """Non-admin user cannot access admin create endpoint."""
        # POST create user
        # assert response.status_code == 403
        regular_user = UserWithProfileFactory(verified=True)
        regular_key = self.client.post('/api/v1/auth/tokens/', {'name': 'test'})
        from accounts.tests.factories import APIKeyFactory
        regular_key = APIKeyFactory(user=regular_user)
        self.authenticate(api_key=regular_key)

        data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'testpass123',
        }
        response = self.client.post('/api/v1/admin/users/', data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_create_duplicate_username_returns_400(self):
        """Creating user with existing username returns error."""
        # POST create with same username
        # assert response.status_code >= 400
        UserWithProfileFactory(username='taken')

        data = {
            'username': 'taken',
            'email': 'new@example.com',
            'password': 'testpass123',
        }
        response = self.client.post('/api/v1/admin/users/', data)
        self.assertGreaterEqual(response.status_code, 400)


class AdminUserListTest(StormCloudAdminTestCase):
    """Tests for GET /api/v1/admin/users/"""

    def test_admin_list_users_returns_all_users(self):
        """Admin can list all users."""
        # GET /api/v1/admin/users/
        # assert response.status_code == 200
        # assert 'users' in response.data
        # Verify count matches expected
        UserWithProfileFactory()
        UserWithProfileFactory()

        response = self.client.get('/api/v1/admin/users/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('users', response.data)
        # At least 4 users: self.user, self.admin, and 2 created above
        self.assertGreaterEqual(response.data['total'], 4)

    def test_admin_list_users_filter_by_is_active(self):
        """Admin can filter users by is_active."""
        # GET /api/v1/admin/users/?is_active=true
        # Verify only active users returned
        active_user = UserWithProfileFactory(is_active=True)
        inactive_user = UserWithProfileFactory(is_active=False)

        response = self.client.get('/api/v1/admin/users/?is_active=true')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check that inactive user is not in results
        usernames = [u['username'] for u in response.data['users']]
        self.assertNotIn(inactive_user.username, usernames)

    def test_admin_list_users_filter_by_is_verified(self):
        """Admin can filter users by email verification status."""
        # GET /api/v1/admin/users/?is_verified=true
        # Verify only verified users returned
        verified_user = UserWithProfileFactory(verified=True, username='verified1')
        unverified_user = UserWithProfileFactory(username='unverified1')

        response = self.client.get('/api/v1/admin/users/?is_verified=true')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check that unverified user is not in results
        usernames = [u['username'] for u in response.data['users']]
        self.assertNotIn(unverified_user.username, usernames)

    def test_admin_list_users_search_by_username(self):
        """Admin can search users by username."""
        # GET /api/v1/admin/users/?search=alice
        # Verify only matching users returned
        alice = UserWithProfileFactory(username='alice')
        bob = UserWithProfileFactory(username='bob')

        response = self.client.get('/api/v1/admin/users/?search=alice')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        usernames = [u['username'] for u in response.data['users']]
        self.assertIn('alice', usernames)
        self.assertNotIn('bob', usernames)

    def test_admin_list_users_search_by_email(self):
        """Admin can search users by email."""
        # GET /api/v1/admin/users/?search=example.com
        # Verify matching users returned
        user1 = UserWithProfileFactory(email='test@example.com')
        user2 = UserWithProfileFactory(email='test@other.com')

        response = self.client.get('/api/v1/admin/users/?search=example.com')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        emails = [u['email'] for u in response.data['users']]
        # Should have at least user1's email
        self.assertTrue(any('example.com' in e for e in emails))

    def test_non_admin_cannot_list_users(self):
        """Non-admin cannot access user list."""
        # GET list
        # assert response.status_code == 403
        regular_user = UserWithProfileFactory(verified=True)
        from accounts.tests.factories import APIKeyFactory
        regular_key = APIKeyFactory(user=regular_user)
        self.authenticate(api_key=regular_key)

        response = self.client.get('/api/v1/admin/users/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AdminUserDetailTest(StormCloudAdminTestCase):
    """Tests for GET /api/v1/admin/users/{id}/"""

    def test_admin_get_user_details_succeeds(self):
        """Admin can get detailed user info."""
        # GET /api/v1/admin/users/{user.id}/
        # assert response.status_code == 200
        # Verify user, profile, and api_keys in response
        from accounts.tests.factories import APIKeyFactory
        user = UserWithProfileFactory()
        APIKeyFactory(user=user)

        response = self.client.get(f'/api/v1/admin/users/{user.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('user', response.data)
        self.assertIn('profile', response.data)
        self.assertIn('api_keys', response.data)

    def test_admin_get_nonexistent_user_returns_404(self):
        """Getting details for non-existent user returns 404."""
        # assert response.status_code == 404
        response = self.client.get('/api/v1/admin/users/99999/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_admin_cannot_get_user_details(self):
        """Non-admin cannot access user details."""
        # GET user details
        # assert response.status_code == 403
        regular_user = UserWithProfileFactory(verified=True)
        from accounts.tests.factories import APIKeyFactory
        regular_key = APIKeyFactory(user=regular_user)
        self.authenticate(api_key=regular_key)

        target_user = UserWithProfileFactory()
        response = self.client.get(f'/api/v1/admin/users/{target_user.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AdminUserVerifyTest(StormCloudAdminTestCase):
    """Tests for POST /api/v1/admin/users/{id}/verify/"""

    def test_admin_verify_user_email_succeeds(self):
        """Admin can manually verify user's email."""
        # POST /api/v1/admin/users/{user.id}/verify/
        # assert response.status_code == 200
        # Refresh profile, assert is_email_verified == True
        user = UserWithProfileFactory()

        response = self.client.post(f'/api/v1/admin/users/{user.id}/verify/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        user.profile.refresh_from_db()
        self.assertTrue(user.profile.is_email_verified)

    def test_admin_verify_nonexistent_user_returns_404(self):
        """Verifying non-existent user returns 404."""
        # assert response.status_code == 404
        response = self.client.post('/api/v1/admin/users/99999/verify/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class AdminUserDeactivateTest(StormCloudAdminTestCase):
    """Tests for POST /api/v1/admin/users/{id}/deactivate/"""

    def test_admin_deactivate_user_succeeds(self):
        """Admin can deactivate user account."""
        # POST /api/v1/admin/users/{user.id}/deactivate/
        # assert response.status_code == 200
        # Verify user.is_active == False
        # Verify keys were revoked
        from accounts.tests.factories import APIKeyFactory
        from accounts.models import APIKey
        user = UserWithProfileFactory(is_active=True)
        key = APIKeyFactory(user=user)

        response = self.client.post(f'/api/v1/admin/users/{user.id}/deactivate/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        user.refresh_from_db()
        self.assertFalse(user.is_active)

        # Verify keys were revoked
        key.refresh_from_db()
        self.assertFalse(key.is_active)

    def test_admin_deactivate_nonexistent_user_returns_404(self):
        """Deactivating non-existent user returns 404."""
        # assert response.status_code == 404
        response = self.client.post('/api/v1/admin/users/99999/deactivate/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class AdminUserActivateTest(StormCloudAdminTestCase):
    """Tests for POST /api/v1/admin/users/{id}/activate/"""

    def test_admin_activate_user_succeeds(self):
        """Admin can reactivate deactivated user."""
        # POST /api/v1/admin/users/{user.id}/activate/
        # assert response.status_code == 200
        # Verify user.is_active == True
        user = UserWithProfileFactory(is_active=False)

        response = self.client.post(f'/api/v1/admin/users/{user.id}/activate/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_admin_activate_does_not_restore_revoked_keys(self):
        """Activating user does not restore revoked API keys."""
        # POST activate
        # Verify keys remain revoked
        from accounts.tests.factories import APIKeyFactory
        user = UserWithProfileFactory(is_active=False)
        key = APIKeyFactory(user=user, revoked=True)

        response = self.client.post(f'/api/v1/admin/users/{user.id}/activate/')

        key.refresh_from_db()
        self.assertFalse(key.is_active)

    def test_admin_activate_nonexistent_user_returns_404(self):
        """Activating non-existent user returns 404."""
        # assert response.status_code == 404
        response = self.client.post('/api/v1/admin/users/99999/activate/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
