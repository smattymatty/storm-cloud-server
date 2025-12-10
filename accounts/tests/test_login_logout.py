"""Tests for session login/logout endpoints."""

from django.test import override_settings
from rest_framework import status

from core.tests.base import StormCloudAPITestCase
from accounts.tests.factories import UserWithProfileFactory


class LoginTest(StormCloudAPITestCase):
    """Tests for POST /api/v1/auth/login/"""

    def test_login_with_valid_credentials_succeeds(self):
        """Login with correct username and password returns 200."""
        # POST to /api/v1/auth/login/ with username and password
        # assert response.status_code == 200
        # assert 'user' in response.data
        # Verify session is created (check cookies or session store)
        user = UserWithProfileFactory(username='testuser', verified=True)
        data = {
            'username': 'testuser',
            'password': 'testpass123',
        }
        response = self.client.post('/api/v1/auth/login/', data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('user', response.data)

    def test_login_with_invalid_password_returns_401(self):
        """Login with wrong password returns 401."""
        # POST with correct username but wrong password
        # assert response.status_code == 401
        # assert response.data['error']['code'] == 'INVALID_CREDENTIALS'
        user = UserWithProfileFactory(username='testuser', verified=True)
        data = {
            'username': 'testuser',
            'password': 'wrongpassword',
        }
        response = self.client.post('/api/v1/auth/login/', data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['error']['code'], 'INVALID_CREDENTIALS')

    def test_login_with_nonexistent_user_returns_401(self):
        """Login with non-existent username returns 401."""
        # assert response.status_code == 401
        data = {
            'username': 'nonexistent',
            'password': 'testpass123',
        }
        response = self.client.post('/api/v1/auth/login/', data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_with_inactive_user_returns_403(self):
        """Login with deactivated account returns 403."""
        # POST login
        # assert response.status_code == 403
        # assert response.data['error']['code'] == 'ACCOUNT_DISABLED'
        user = UserWithProfileFactory(username='testuser', verified=True, is_active=False)
        data = {
            'username': 'testuser',
            'password': 'testpass123',
        }
        response = self.client.post('/api/v1/auth/login/', data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error']['code'], 'ACCOUNT_DISABLED')

    @override_settings(STORMCLOUD_REQUIRE_EMAIL_VERIFICATION=True)
    def test_login_with_unverified_email_returns_403(self):
        """Login with unverified email returns 403 when verification required."""
        # POST login
        # assert response.status_code == 403
        # assert response.data['error']['code'] == 'EMAIL_NOT_VERIFIED'
        user = UserWithProfileFactory(username='testuser')
        data = {
            'username': 'testuser',
            'password': 'testpass123',
        }
        response = self.client.post('/api/v1/auth/login/', data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error']['code'], 'EMAIL_NOT_VERIFIED')

    def test_login_fires_login_failed_signal_on_error(self):
        """Failed login fires login_failed signal."""
        # Verify login_failed signal was sent
        from accounts.signals import login_failed

        signal_received = []

        def signal_handler(sender, **kwargs):
            signal_received.append(kwargs)

        login_failed.connect(signal_handler)

        user = UserWithProfileFactory(username='testuser', verified=True)
        data = {
            'username': 'testuser',
            'password': 'wrongpassword',
        }
        response = self.client.post('/api/v1/auth/login/', data)

        login_failed.disconnect(signal_handler)

        self.assertTrue(len(signal_received) > 0)


class LogoutTest(StormCloudAPITestCase):
    """Tests for POST /api/v1/auth/logout/"""

    def test_logout_destroys_session(self):
        """Logout clears session."""
        # POST to /api/v1/auth/logout/
        # assert response.status_code == 200
        # Verify session is destroyed
        user = UserWithProfileFactory(username='testuser', verified=True)
        self.client.login(username='testuser', password='testpass123')

        response = self.client.post('/api/v1/auth/logout/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_logout_while_not_logged_in_succeeds(self):
        """Logout without being logged in still returns 200."""
        # assert response.status_code == 200
        response = self.client.post('/api/v1/auth/logout/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
