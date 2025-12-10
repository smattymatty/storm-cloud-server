"""Tests for API key management endpoints."""

from django.test import override_settings
from rest_framework import status

from core.tests.base import StormCloudAPITestCase
from accounts.tests.factories import UserWithProfileFactory, APIKeyFactory
from accounts.models import APIKey


class APIKeyCreateTest(StormCloudAPITestCase):
    """Tests for POST /api/v1/auth/keys/create/"""

    def test_create_api_key_succeeds(self):
        """Creating API key returns key (only time shown)."""
        # POST to /api/v1/auth/keys/create/ with name='test-key'
        # assert response.status_code == 201
        # assert 'key' in response.data
        # assert response.data['name'] == 'test-key'
        # Verify key was saved to DB
        self.authenticate()
        data = {'name': 'test-key'}
        response = self.client.post('/api/v1/auth/tokens/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('key', response.data)
        self.assertEqual(response.data['name'], 'test-key')

        # Verify key was saved
        self.assertTrue(APIKey.objects.filter(user=self.user, name='test-key').exists())

    @override_settings(STORMCLOUD_REQUIRE_EMAIL_VERIFICATION=True)
    def test_create_api_key_with_unverified_email_returns_403(self):
        """Creating API key with unverified email returns 403."""
        # Authenticate
        # POST create key
        # assert response.status_code == 403
        # assert response.data['error']['code'] == 'EMAIL_NOT_VERIFIED'
        unverified_user = UserWithProfileFactory()
        unverified_key = APIKeyFactory(user=unverified_user)
        self.authenticate(api_key=unverified_key)

        data = {'name': 'test-key'}
        response = self.client.post('/api/v1/auth/tokens/', data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error']['code'], 'EMAIL_NOT_VERIFIED')

    @override_settings(STORMCLOUD_MAX_API_KEYS_PER_USER=2)
    def test_create_api_key_when_max_exceeded_returns_403(self):
        """Creating API key when at limit returns 403."""
        # POST create third key
        # assert response.status_code == 403
        # assert response.data['error']['code'] == 'MAX_KEYS_EXCEEDED'
        # Create 2 active keys (including the one from setUp)
        APIKeyFactory(user=self.user)
        self.authenticate()

        data = {'name': 'third-key'}
        response = self.client.post('/api/v1/auth/tokens/', data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error']['code'], 'MAX_KEYS_EXCEEDED')

    def test_create_api_key_fires_signal(self):
        """Creating API key fires api_key_created signal."""
        from accounts.signals import api_key_created

        signal_received = []

        def signal_handler(sender, **kwargs):
            signal_received.append(kwargs)

        api_key_created.connect(signal_handler)

        self.authenticate()
        data = {'name': 'test-key'}
        response = self.client.post('/api/v1/auth/tokens/', data)

        api_key_created.disconnect(signal_handler)

        self.assertTrue(len(signal_received) > 0)


class APIKeyListTest(StormCloudAPITestCase):
    """Tests for GET /api/v1/auth/keys/"""

    def test_list_api_keys_returns_user_keys(self):
        """Listing keys returns only current user's keys."""
        # Create 2 keys for user
        # Create 1 key for different user
        # GET /api/v1/auth/keys/
        # assert response.status_code == 200
        # assert response.data['total'] == 2
        # assert len(response.data['keys']) == 2
        self.authenticate()
        # One key already exists from setUp, create another
        APIKeyFactory(user=self.user)

        # Create key for different user
        other_user = UserWithProfileFactory()
        APIKeyFactory(user=other_user)

        response = self.client.get('/api/v1/auth/tokens/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total'], 2)
        self.assertEqual(len(response.data['keys']), 2)

    def test_list_api_keys_does_not_include_key_value(self):
        """Listing keys doesn't expose actual key values."""
        # GET list
        # Verify 'key' field is not in response data
        self.authenticate()

        response = self.client.get('/api/v1/auth/tokens/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check that key field is not in any token
        for key_data in response.data['keys']:
            self.assertNotIn('key', key_data)

    def test_list_api_keys_includes_revoked_keys(self):
        """Listing keys includes revoked keys."""
        # GET list
        # Verify both appear in response
        self.authenticate()
        revoked_key = APIKeyFactory(user=self.user, revoked=True)

        response = self.client.get('/api/v1/auth/tokens/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should have 2 keys: one active from setUp, one revoked
        self.assertEqual(response.data['total'], 2)


class APIKeyRevokeTest(StormCloudAPITestCase):
    """Tests for POST /api/v1/auth/keys/{id}/revoke/"""

    def test_revoke_own_api_key_succeeds(self):
        """Revoking own key succeeds."""
        # POST to /api/v1/auth/keys/{key.id}/revoke/
        # assert response.status_code == 200
        # Refresh key from DB, assert is_active == False
        # assert revoked_at is not None
        self.authenticate()
        key_to_revoke = APIKeyFactory(user=self.user)

        response = self.client.post(f'/api/v1/auth/tokens/{key_to_revoke.id}/revoke/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        key_to_revoke.refresh_from_db()
        self.assertFalse(key_to_revoke.is_active)
        self.assertIsNotNone(key_to_revoke.revoked_at)

    def test_revoke_nonexistent_key_returns_404(self):
        """Revoking non-existent key returns 404."""
        # assert response.status_code == 404
        # assert response.data['error']['code'] == 'KEY_NOT_FOUND'
        import uuid

        self.authenticate()
        fake_id = uuid.uuid4()

        response = self.client.post(f'/api/v1/auth/tokens/{fake_id}/revoke/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['error']['code'], 'KEY_NOT_FOUND')

    def test_revoke_another_users_key_returns_404(self):
        """Revoking another user's key returns 404."""
        # Authenticate as self.user
        # POST revoke other user's key
        # assert response.status_code == 404
        other_user = UserWithProfileFactory()
        other_key = APIKeyFactory(user=other_user)

        self.authenticate()

        response = self.client.post(f'/api/v1/auth/tokens/{other_key.id}/revoke/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_revoke_already_revoked_key_returns_400(self):
        """Revoking already revoked key returns 400."""
        # POST revoke
        # assert response.status_code == 400
        # assert response.data['error']['code'] == 'ALREADY_REVOKED'
        self.authenticate()
        revoked_key = APIKeyFactory(user=self.user, revoked=True)

        response = self.client.post(f'/api/v1/auth/tokens/{revoked_key.id}/revoke/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'ALREADY_REVOKED')

    def test_revoke_fires_signal(self):
        """Revoking key fires api_key_revoked signal."""
        from accounts.signals import api_key_revoked

        signal_received = []

        def signal_handler(sender, **kwargs):
            signal_received.append(kwargs)

        api_key_revoked.connect(signal_handler)

        self.authenticate()
        key_to_revoke = APIKeyFactory(user=self.user)
        response = self.client.post(f'/api/v1/auth/tokens/{key_to_revoke.id}/revoke/')

        api_key_revoked.disconnect(signal_handler)

        self.assertTrue(len(signal_received) > 0)
