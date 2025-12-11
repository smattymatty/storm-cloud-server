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

    def test_admin_create_user_with_names_succeeds(self):
        """Admin can create user with first and last name."""
        data = {
            'username': 'johndoe',
            'email': 'john@example.com',
            'password': 'testpass123',
            'first_name': 'John',
            'last_name': 'Doe',
        }
        response = self.client.post('/api/v1/admin/users/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(username='johndoe')
        self.assertEqual(user.first_name, 'John')
        self.assertEqual(user.last_name, 'Doe')


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


class AdminUserUpdateTest(StormCloudAdminTestCase):
    """Tests for PATCH /api/v1/admin/users/{id}/"""

    def test_admin_update_user_email_succeeds(self):
        """Admin can update user's email."""
        user = UserWithProfileFactory(email='old@example.com')

        data = {'email': 'new@example.com'}
        response = self.client.patch(f'/api/v1/admin/users/{user.id}/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        user.refresh_from_db()
        self.assertEqual(user.email, 'new@example.com')

    def test_admin_update_user_name_succeeds(self):
        """Admin can update user's first and last name."""
        user = UserWithProfileFactory(first_name='John', last_name='Doe')

        data = {'first_name': 'Jane', 'last_name': 'Smith'}
        response = self.client.patch(f'/api/v1/admin/users/{user.id}/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        user.refresh_from_db()
        self.assertEqual(user.first_name, 'Jane')
        self.assertEqual(user.last_name, 'Smith')

    def test_admin_update_user_is_staff_succeeds(self):
        """Admin can promote/demote user to staff."""
        user = UserWithProfileFactory(is_staff=False)

        data = {'is_staff': True}
        response = self.client.patch(f'/api/v1/admin/users/{user.id}/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        user.refresh_from_db()
        self.assertTrue(user.is_staff)

    def test_admin_update_user_password_succeeds(self):
        """Admin can reset user's password."""
        user = UserWithProfileFactory()

        data = {'password': 'newpassword123'}
        response = self.client.patch(f'/api/v1/admin/users/{user.id}/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        user.refresh_from_db()
        self.assertTrue(user.check_password('newpassword123'))

    def test_admin_update_duplicate_email_returns_400(self):
        """Updating to existing email returns error."""
        user1 = UserWithProfileFactory(email='taken@example.com')
        user2 = UserWithProfileFactory(email='other@example.com')

        data = {'email': 'taken@example.com'}
        response = self.client.patch(f'/api/v1/admin/users/{user2.id}/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_update_nonexistent_user_returns_404(self):
        """Updating non-existent user returns 404."""
        data = {'email': 'new@example.com'}
        response = self.client.patch('/api/v1/admin/users/99999/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_admin_cannot_update_user(self):
        """Non-admin cannot update user details."""
        regular_user = UserWithProfileFactory(verified=True)
        from accounts.tests.factories import APIKeyFactory
        regular_key = APIKeyFactory(user=regular_user)
        self.authenticate(api_key=regular_key)

        target_user = UserWithProfileFactory()
        data = {'email': 'new@example.com'}
        response = self.client.patch(f'/api/v1/admin/users/{target_user.id}/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AdminUserDeleteTest(StormCloudAdminTestCase):
    """Tests for DELETE /api/v1/admin/users/{id}/"""

    def test_admin_delete_user_succeeds(self):
        """Admin can delete user account."""
        user = UserWithProfileFactory()
        user_id = user.id

        response = self.client.delete(f'/api/v1/admin/users/{user_id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify user was deleted
        self.assertFalse(User.objects.filter(id=user_id).exists())

    def test_admin_cannot_delete_self(self):
        """Admin cannot delete their own account."""
        response = self.client.delete(f'/api/v1/admin/users/{self.admin.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Verify admin still exists
        self.assertTrue(User.objects.filter(id=self.admin.id).exists())

    def test_admin_cannot_delete_last_superuser(self):
        """Cannot delete the last active superuser."""
        # Make admin the only superuser
        User.objects.filter(is_superuser=True).exclude(id=self.admin.id).delete()

        # Create another admin to perform the deletion attempt
        other_admin = UserWithProfileFactory(is_staff=True, is_superuser=False)
        from accounts.tests.factories import APIKeyFactory
        admin_key = APIKeyFactory(user=other_admin)
        self.authenticate(api_key=admin_key)

        response = self.client.delete(f'/api/v1/admin/users/{self.admin.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_delete_nonexistent_user_returns_404(self):
        """Deleting non-existent user returns 404."""
        response = self.client.delete('/api/v1/admin/users/99999/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_admin_cannot_delete_user(self):
        """Non-admin cannot delete user."""
        regular_user = UserWithProfileFactory(verified=True)
        from accounts.tests.factories import APIKeyFactory
        regular_key = APIKeyFactory(user=regular_user)
        self.authenticate(api_key=regular_key)

        target_user = UserWithProfileFactory()
        response = self.client.delete(f'/api/v1/admin/users/{target_user.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AdminUserPasswordResetTest(StormCloudAdminTestCase):
    """Tests for POST /api/v1/admin/users/{id}/reset-password/"""

    def test_admin_reset_password_with_new_password_succeeds(self):
        """Admin can set a specific password for user."""
        user = UserWithProfileFactory()

        data = {'new_password': 'temppassword123'}
        response = self.client.post(f'/api/v1/admin/users/{user.id}/reset-password/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        user.refresh_from_db()
        self.assertTrue(user.check_password('temppassword123'))
        self.assertIn('temporary_password', response.data)

    def test_admin_reset_password_with_send_email_succeeds(self):
        """Admin can generate temporary password with send_email flag."""
        user = UserWithProfileFactory(email='test@example.com')

        data = {'send_email': True}
        response = self.client.post(f'/api/v1/admin/users/{user.id}/reset-password/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Password should be changed
        self.assertIn('temporary_password', response.data)
        temp_password = response.data['temporary_password']

        user.refresh_from_db()
        self.assertTrue(user.check_password(temp_password))

    def test_admin_reset_password_without_params_returns_400(self):
        """Password reset without new_password or send_email returns error."""
        user = UserWithProfileFactory()

        data = {}
        response = self.client.post(f'/api/v1/admin/users/{user.id}/reset-password/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_reset_password_nonexistent_user_returns_404(self):
        """Resetting password for non-existent user returns 404."""
        data = {'new_password': 'temppassword123'}
        response = self.client.post('/api/v1/admin/users/99999/reset-password/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_admin_cannot_reset_password(self):
        """Non-admin cannot reset user password."""
        regular_user = UserWithProfileFactory(verified=True)
        from accounts.tests.factories import APIKeyFactory
        regular_key = APIKeyFactory(user=regular_user)
        self.authenticate(api_key=regular_key)

        target_user = UserWithProfileFactory()
        data = {'new_password': 'temppassword123'}
        response = self.client.post(f'/api/v1/admin/users/{target_user.id}/reset-password/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AdminUserDetailIsActiveTest(StormCloudAdminTestCase):
    """Tests for is_active field in user detail responses."""

    def test_user_detail_includes_is_active(self):
        """User detail response includes is_active field."""
        user = UserWithProfileFactory(is_active=True)

        response = self.client.get(f'/api/v1/admin/users/{user.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertIn('user', response.data)
        self.assertIn('is_active', response.data['user'])
        self.assertTrue(response.data['user']['is_active'])

    def test_user_detail_shows_inactive_status(self):
        """User detail correctly shows inactive status."""
        user = UserWithProfileFactory(is_active=False)

        response = self.client.get(f'/api/v1/admin/users/{user.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertFalse(response.data['user']['is_active'])
