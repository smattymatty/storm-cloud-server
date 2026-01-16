"""Tests for account management endpoints."""

from django.contrib.auth import get_user_model
from rest_framework import status

from core.tests.base import StormCloudAPITestCase
from accounts.tests.factories import UserWithProfileFactory, APIKeyFactory
from accounts.models import Account, APIKey

User = get_user_model()


class AuthMeTest(StormCloudAPITestCase):
    """Tests for GET /api/v1/auth/me/"""

    def test_auth_me_returns_user_info(self):
        """GET /auth/me/ returns user, account, and current API key info."""
        # Use session auth to get full user/account response
        self.authenticate_session(self.user)
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("user", response.data)
        self.assertIn("account", response.data)
        self.assertIn("api_key", response.data)
        self.assertEqual(response.data["user"]["username"], self.user.username)

    def test_auth_me_without_authentication_returns_401(self):
        """GET /auth/me/ without auth returns 403."""
        # GET /auth/me/
        # Note: DRF returns 403 for unauthenticated requests with IsAuthenticated permission
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class DeactivateAccountTest(StormCloudAPITestCase):
    """Tests for POST /api/v1/auth/account/deactivate/"""

    def test_deactivate_account_with_correct_password_succeeds(self):
        """Deactivating account with correct password succeeds."""
        # Create a couple API keys for user
        # POST to /api/v1/auth/account/deactivate/ with password='testpass123'
        # assert response.status_code == 200
        # Refresh user from DB, assert is_active == False
        # Verify all keys were revoked
        self.authenticate_session(
            self.user
        )  # Session auth required for account management
        key2 = APIKeyFactory(organization=self.user.account.organization)

        data = {"password": "testpass123"}
        response = self.client.post("/api/v1/auth/deactivate/", data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

        # Verify all keys were revoked
        for key in APIKey.objects.filter(organization=self.user.account.organization):
            self.assertFalse(key.is_active)

    def test_deactivate_account_with_wrong_password_returns_400(self):
        """Deactivating account with wrong password returns 400."""
        # POST deactivate with password='wrongpassword'
        # assert response.status_code == 400
        # assert response.data['error']['code'] == 'INVALID_PASSWORD'
        self.authenticate_session(self.user)  # Session auth required

        data = {"password": "wrongpassword"}
        response = self.client.post("/api/v1/auth/deactivate/", data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "INVALID_PASSWORD")

    def test_deactivate_fires_signal(self):
        """Deactivating account fires account_deactivated signal."""
        from accounts.signals import account_deactivated

        signal_received = []

        def signal_handler(sender, **kwargs):
            signal_received.append(kwargs)

        account_deactivated.connect(signal_handler)

        self.authenticate_session(self.user)  # Session auth required
        data = {"password": "testpass123"}
        response = self.client.post("/api/v1/auth/deactivate/", data)

        account_deactivated.disconnect(signal_handler)

        self.assertTrue(len(signal_received) > 0)


class DeleteAccountTest(StormCloudAPITestCase):
    """Tests for DELETE /api/v1/auth/account/delete/"""

    def test_delete_account_with_correct_password_succeeds(self):
        """Deleting account with correct password removes user."""
        # Note user ID
        # DELETE /api/v1/auth/account/delete/ with password in body
        # assert response.status_code == 200
        # Verify user no longer exists in DB
        self.authenticate_session(self.user)  # Session auth required
        user_id = self.user.id

        data = {"password": "testpass123"}
        response = self.client.delete("/api/v1/auth/delete/", data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify user no longer exists
        self.assertFalse(User.objects.filter(id=user_id).exists())

    def test_delete_account_with_wrong_password_returns_400(self):
        """Deleting account with wrong password returns 400."""
        # assert response.status_code == 400
        # assert response.data['error']['code'] == 'INVALID_PASSWORD'
        self.authenticate_session(self.user)  # Session auth required

        data = {"password": "wrongpassword"}
        response = self.client.delete("/api/v1/auth/delete/", data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "INVALID_PASSWORD")

    def test_delete_account_cascades_to_profile(self):
        """Deleting account also deletes profile but org API keys remain."""
        # API keys are org-scoped, not user-scoped, so they don't cascade
        self.authenticate_session(self.user)  # Session auth required
        profile_id = self.user.account.id
        key_id = self.api_key.id

        data = {"password": "testpass123"}
        response = self.client.delete("/api/v1/auth/delete/", data)

        # Account is deleted
        self.assertFalse(Account.objects.filter(id=profile_id).exists())
        # API key remains (org-scoped) but created_by is now None
        self.assertTrue(APIKey.objects.filter(id=key_id).exists())

    def test_delete_fires_signal(self):
        """Deleting account fires account_deleted signal."""
        from accounts.signals import account_deleted

        signal_received = []

        def signal_handler(sender, **kwargs):
            signal_received.append(kwargs)

        account_deleted.connect(signal_handler)

        self.authenticate_session(self.user)  # Session auth required
        data = {"password": "testpass123"}
        response = self.client.delete("/api/v1/auth/delete/", data)

        account_deleted.disconnect(signal_handler)

        self.assertTrue(len(signal_received) > 0)
        self.assertIn("user_id", signal_received[0])
        self.assertIn("username", signal_received[0])
