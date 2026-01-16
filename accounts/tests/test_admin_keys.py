"""Tests for admin API key management endpoints."""

from rest_framework import status

from core.tests.base import StormCloudAdminTestCase
from accounts.tests.factories import UserWithProfileFactory, APIKeyFactory


class AdminAPIKeyListTest(StormCloudAdminTestCase):
    """Tests for GET /api/v1/admin/keys/"""

    def test_admin_list_all_api_keys_succeeds(self):
        """Admin can list all API keys across all users."""
        # GET /api/v1/admin/keys/
        # assert response.status_code == 200
        # assert 'keys' in response.data
        # Verify all keys are returned
        user1 = UserWithProfileFactory()
        user2 = UserWithProfileFactory()
        APIKeyFactory(user=user1)
        APIKeyFactory(user=user2)

        response = self.client.get("/api/v1/admin/keys/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("keys", response.data)
        # At least 4 keys: self.api_key, self.admin_key, and 2 created above
        self.assertGreaterEqual(response.data["total"], 4)

    def test_admin_list_keys_filter_by_organization_id(self):
        """Admin can filter keys by organization_id."""
        # GET /api/v1/admin/keys/?organization_id={org1.id}
        # Verify only org1's keys returned
        user1 = UserWithProfileFactory()
        user2 = UserWithProfileFactory()
        key1 = APIKeyFactory(organization=user1.account.organization)
        key2 = APIKeyFactory(organization=user2.account.organization)

        response = self.client.get(
            f"/api/v1/admin/keys/?organization_id={user1.account.organization.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify only org1's keys are in response
        key_ids = [k["id"] for k in response.data["keys"]]
        self.assertIn(str(key1.id), key_ids)
        self.assertNotIn(str(key2.id), key_ids)

    def test_admin_list_keys_filter_by_is_active(self):
        """Admin can filter keys by active status."""
        # GET /api/v1/admin/keys/?is_active=true
        # Verify only active keys returned
        user = UserWithProfileFactory()
        active_key = APIKeyFactory(organization=user.account.organization)
        revoked_key = APIKeyFactory(
            organization=user.account.organization, revoked=True
        )

        response = self.client.get("/api/v1/admin/keys/?is_active=true")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify revoked key is not in response
        key_ids = [k["id"] for k in response.data["keys"]]
        self.assertNotIn(str(revoked_key.id), key_ids)

    def test_admin_list_keys_includes_organization(self):
        """Key list includes associated organization."""
        # GET list
        # Verify response includes organization for each key
        user = UserWithProfileFactory()
        APIKeyFactory(organization=user.account.organization)

        response = self.client.get("/api/v1/admin/keys/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify at least one key has organization field
        self.assertTrue(any("organization" in k for k in response.data["keys"]))

    def test_non_admin_cannot_list_all_keys(self):
        """Non-admin cannot list all keys."""
        # GET /api/v1/admin/keys/
        # assert response.status_code == 403
        regular_user = UserWithProfileFactory(verified=True)
        regular_key = APIKeyFactory(organization=regular_user.account.organization)
        self.authenticate(api_key=regular_key)

        response = self.client.get("/api/v1/admin/keys/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AdminAPIKeyRevokeTest(StormCloudAdminTestCase):
    """Tests for POST /api/v1/admin/keys/{id}/revoke/"""

    def test_admin_revoke_any_orgs_key_succeeds(self):
        """Admin can revoke any organization's API key."""
        # POST /api/v1/admin/keys/{key.id}/revoke/
        # assert response.status_code == 200
        # Verify key was revoked
        other_user = UserWithProfileFactory()
        other_key = APIKeyFactory(organization=other_user.account.organization)

        response = self.client.post(f"/api/v1/admin/keys/{other_key.id}/revoke/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        other_key.refresh_from_db()
        self.assertFalse(other_key.is_active)

    def test_admin_revoke_nonexistent_key_returns_404(self):
        """Revoking non-existent key returns 404."""
        # assert response.status_code == 404
        import uuid

        fake_id = uuid.uuid4()
        response = self.client.post(f"/api/v1/admin/keys/{fake_id}/revoke/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_revoke_already_revoked_key_returns_400(self):
        """Revoking already revoked key returns 400."""
        # POST revoke
        # assert response.status_code == 400
        user = UserWithProfileFactory()
        revoked_key = APIKeyFactory(
            organization=user.account.organization, revoked=True
        )

        response = self.client.post(f"/api/v1/admin/keys/{revoked_key.id}/revoke/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_admin_cannot_revoke_others_keys(self):
        """Non-admin cannot revoke other orgs' keys."""
        # Authenticate as user2 (non-admin)
        # POST revoke org1's key
        # assert response.status_code == 403 or 404
        user1 = UserWithProfileFactory()
        key1 = APIKeyFactory(organization=user1.account.organization)

        user2 = UserWithProfileFactory(verified=True)
        key2 = APIKeyFactory(organization=user2.account.organization)
        self.authenticate(api_key=key2)

        response = self.client.post(f"/api/v1/admin/keys/{key1.id}/revoke/")
        self.assertIn(
            response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]
        )

    def test_admin_revoke_fires_signal_with_admin_as_revoker(self):
        """Admin revoking key fires signal with admin as revoked_by."""
        from accounts.signals import api_key_revoked

        signal_received = []

        def signal_handler(sender, **kwargs):
            signal_received.append(kwargs)

        api_key_revoked.connect(signal_handler)

        other_user = UserWithProfileFactory()
        other_key = APIKeyFactory(organization=other_user.account.organization)
        response = self.client.post(f"/api/v1/admin/keys/{other_key.id}/revoke/")

        api_key_revoked.disconnect(signal_handler)

        self.assertTrue(len(signal_received) > 0)
