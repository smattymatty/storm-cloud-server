"""Tests for webhook configuration endpoints."""

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import APIKey, Account, Organization
from django.contrib.auth import get_user_model

User = get_user_model()


class WebhookConfigTests(TestCase):
    """Tests for webhook configuration endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.org = Organization.objects.create(name="Test Org", slug="test-org")
        Account.objects.create(user=self.user, organization=self.org, email_verified=True)
        self.api_key = APIKey.objects.create(organization=self.org, name="test-key")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.api_key.key}")

    def test_get_webhook_config_empty(self):
        """GET returns empty config initially."""
        response = self.client.get("/api/v1/account/webhook/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["webhook_url"])
        self.assertFalse(response.data["webhook_enabled"])
        self.assertIsNone(response.data["webhook_secret"])

    def test_set_webhook_url(self):
        """PUT sets webhook URL and generates secret."""
        response = self.client.put(
            "/api/v1/account/webhook/",
            {"webhook_url": "https://example.com/webhook/"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["webhook_url"], "https://example.com/webhook/")
        self.assertTrue(response.data["webhook_enabled"])
        self.assertIsNotNone(response.data["webhook_secret"])
        self.assertEqual(len(response.data["webhook_secret"]), 64)  # 32 bytes hex

    def test_set_webhook_url_localhost(self):
        """PUT allows localhost URLs (for development)."""
        response = self.client.put(
            "/api/v1/account/webhook/",
            {"webhook_url": "http://localhost:8000/webhook/"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["webhook_url"], "http://localhost:8000/webhook/")

    def test_invalid_url_rejected(self):
        """PUT rejects invalid URLs."""
        response = self.client.put(
            "/api/v1/account/webhook/", {"webhook_url": "not-a-url"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_update_webhook_url(self):
        """PUT updates existing webhook URL."""
        # Set initial URL
        self.api_key.webhook_url = "https://old.example.com/webhook/"
        self.api_key.save()
        old_secret = self.api_key.webhook_secret

        # Update URL
        response = self.client.put(
            "/api/v1/account/webhook/",
            {"webhook_url": "https://new.example.com/webhook/"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["webhook_url"], "https://new.example.com/webhook/")
        self.assertEqual(response.data["message"], "Webhook URL updated.")
        # Secret should remain the same when just updating URL
        self.assertEqual(response.data["webhook_secret"], old_secret)

    def test_delete_webhook(self):
        """DELETE clears webhook config."""
        # First set a webhook
        self.api_key.webhook_url = "https://example.com/webhook/"
        self.api_key.save()

        # Then delete it
        response = self.client.delete("/api/v1/account/webhook/")
        self.assertEqual(response.status_code, 200)

        self.api_key.refresh_from_db()
        self.assertIsNone(self.api_key.webhook_url)
        self.assertIsNone(self.api_key.webhook_secret)
        self.assertFalse(self.api_key.webhook_enabled)

    def test_disable_webhook_via_empty_put(self):
        """PUT with empty URL disables webhook."""
        # Set webhook first
        self.api_key.webhook_url = "https://example.com/webhook/"
        self.api_key.save()

        # Disable via empty PUT
        response = self.client.put(
            "/api/v1/account/webhook/", {"webhook_url": ""}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["message"], "Webhook disabled.")

        self.api_key.refresh_from_db()
        self.assertIsNone(self.api_key.webhook_url)

    def test_regenerate_secret(self):
        """POST regenerate creates new secret."""
        # Set webhook first
        self.api_key.webhook_url = "https://example.com/webhook/"
        self.api_key.save()
        old_secret = self.api_key.webhook_secret

        response = self.client.post("/api/v1/account/webhook/regenerate-secret/")
        self.assertEqual(response.status_code, 200)

        self.api_key.refresh_from_db()
        self.assertNotEqual(self.api_key.webhook_secret, old_secret)
        self.assertEqual(len(self.api_key.webhook_secret), 64)

    def test_regenerate_without_webhook_fails(self):
        """Can't regenerate secret without webhook URL."""
        response = self.client.post("/api/v1/account/webhook/regenerate-secret/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("No webhook configured", response.data["error"])

    def test_webhook_requires_auth(self):
        """Webhook endpoints require authentication."""
        client = APIClient()  # No auth
        response = client.get("/api/v1/account/webhook/")
        self.assertEqual(response.status_code, 403)


class WebhookSecretGenerationTests(TestCase):
    """Tests for webhook secret auto-generation."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.org = Organization.objects.create(name="Test Org", slug="test-org")
        Account.objects.create(user=self.user, organization=self.org, email_verified=True)

    def test_secret_generated_on_url_set(self):
        """Secret is auto-generated when URL is set."""
        api_key = APIKey.objects.create(organization=self.org, name="test")
        self.assertIsNone(api_key.webhook_secret)

        api_key.webhook_url = "https://example.com/webhook/"
        api_key.save()

        self.assertIsNotNone(api_key.webhook_secret)
        self.assertEqual(len(api_key.webhook_secret), 64)

    def test_secret_cleared_on_url_removed(self):
        """Secret is cleared when URL is removed."""
        api_key = APIKey.objects.create(
            organization=self.org, name="test", webhook_url="https://example.com/webhook/"
        )
        self.assertIsNotNone(api_key.webhook_secret)

        api_key.webhook_url = None
        api_key.save()

        self.assertIsNone(api_key.webhook_secret)
        self.assertFalse(api_key.webhook_enabled)

    def test_webhook_enabled_auto_set(self):
        """webhook_enabled is automatically set based on URL presence."""
        api_key = APIKey.objects.create(organization=self.org, name="test")
        self.assertFalse(api_key.webhook_enabled)

        api_key.webhook_url = "https://example.com/webhook/"
        api_key.save()
        self.assertTrue(api_key.webhook_enabled)

        api_key.webhook_url = None
        api_key.save()
        self.assertFalse(api_key.webhook_enabled)

    def test_secret_not_regenerated_on_update(self):
        """Existing secret is preserved when updating URL."""
        api_key = APIKey.objects.create(
            organization=self.org, name="test", webhook_url="https://old.example.com/webhook/"
        )
        old_secret = api_key.webhook_secret

        api_key.webhook_url = "https://new.example.com/webhook/"
        api_key.save()

        self.assertEqual(api_key.webhook_secret, old_secret)


class WebhookTestEndpointTests(TestCase):
    """Tests for the webhook test endpoint (without actual HTTP calls)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.org = Organization.objects.create(name="Test Org", slug="test-org")
        Account.objects.create(user=self.user, organization=self.org, email_verified=True)
        self.api_key = APIKey.objects.create(organization=self.org, name="test-key")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.api_key.key}")

    def test_test_webhook_without_url_fails(self):
        """Can't test webhook without URL configured."""
        response = self.client.post("/api/v1/account/webhook/test/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("No webhook configured", response.data["error"])


class AdminWebhookConfigTests(TestCase):
    """Tests for admin webhook configuration endpoints."""

    def setUp(self):
        # Create admin user
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="adminpass"
        )
        self.admin_org = Organization.objects.create(name="Admin Org", slug="admin-org")
        self.admin_account = Account.objects.create(
            user=self.admin, organization=self.admin_org, email_verified=True
        )
        self.admin_key = APIKey.objects.create(
            organization=self.admin_org,
            name="admin-key",
            created_by=self.admin_account,  # Required for APIKeyUser.is_staff
        )

        # Create target user
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.org = Organization.objects.create(name="Test Org", slug="test-org")
        self.user_account = Account.objects.create(
            user=self.user, organization=self.org, email_verified=True
        )
        self.user_key = APIKey.objects.create(
            organization=self.org,
            name="user-key",
            created_by=self.user_account,
        )

        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.admin_key.key}")

    def test_get_webhook_config_empty(self):
        """Admin can get empty webhook config."""
        response = self.client.get(
            f"/api/v1/admin/users/{self.user.id}/keys/{self.user_key.id}/webhook/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["webhook_url"])
        self.assertFalse(response.data["webhook_enabled"])

    def test_get_webhook_config_not_found(self):
        """Returns 404 for non-existent key."""
        import uuid
        response = self.client.get(
            f"/api/v1/admin/users/{self.user.id}/keys/{uuid.uuid4()}/webhook/"
        )
        self.assertEqual(response.status_code, 404)

    def test_set_webhook_url(self):
        """Admin can set webhook URL."""
        response = self.client.put(
            f"/api/v1/admin/users/{self.user.id}/keys/{self.user_key.id}/webhook/",
            {"webhook_url": "https://example.com/webhook/"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["webhook_url"], "https://example.com/webhook/")
        self.assertTrue(response.data["webhook_enabled"])
        self.assertIsNotNone(response.data["webhook_secret"])

    def test_set_invalid_url_rejected(self):
        """Admin cannot set invalid URL."""
        response = self.client.put(
            f"/api/v1/admin/users/{self.user.id}/keys/{self.user_key.id}/webhook/",
            {"webhook_url": "not-a-url"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_disable_webhook(self):
        """Admin can disable webhook via DELETE."""
        # First set a webhook
        self.user_key.webhook_url = "https://example.com/webhook/"
        self.user_key.save()

        response = self.client.delete(
            f"/api/v1/admin/users/{self.user.id}/keys/{self.user_key.id}/webhook/"
        )
        self.assertEqual(response.status_code, 200)

        self.user_key.refresh_from_db()
        self.assertIsNone(self.user_key.webhook_url)
        self.assertFalse(self.user_key.webhook_enabled)

    def test_regenerate_secret(self):
        """Admin can regenerate webhook secret."""
        self.user_key.webhook_url = "https://example.com/webhook/"
        self.user_key.save()
        old_secret = self.user_key.webhook_secret

        response = self.client.post(
            f"/api/v1/admin/users/{self.user.id}/keys/{self.user_key.id}/webhook/regenerate-secret/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.data["webhook_secret"], old_secret)

    def test_regenerate_without_webhook_fails(self):
        """Can't regenerate secret without webhook URL."""
        response = self.client.post(
            f"/api/v1/admin/users/{self.user.id}/keys/{self.user_key.id}/webhook/regenerate-secret/"
        )
        self.assertEqual(response.status_code, 400)

    def test_test_webhook_without_url_fails(self):
        """Can't test webhook without URL configured."""
        response = self.client.post(
            f"/api/v1/admin/users/{self.user.id}/keys/{self.user_key.id}/webhook/test/"
        )
        self.assertEqual(response.status_code, 400)

    def test_requires_admin(self):
        """Non-admin cannot access admin webhook endpoints."""
        # Use non-admin credentials
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.user_key.key}")

        response = self.client.get(
            f"/api/v1/admin/users/{self.user.id}/keys/{self.user_key.id}/webhook/"
        )
        self.assertEqual(response.status_code, 403)


class UserKeyWebhookTests(TestCase):
    """Tests for user per-key webhook endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.org = Organization.objects.create(name="Test Org", slug="test-org")
        Account.objects.create(user=self.user, organization=self.org, email_verified=True)
        self.key1 = APIKey.objects.create(organization=self.org, name="key1")
        self.key2 = APIKey.objects.create(organization=self.org, name="key2")

        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.key1.key}")

    def test_get_webhook_config_empty(self):
        """User can get empty webhook config."""
        response = self.client.get(f"/api/v1/auth/tokens/{self.key1.id}/webhook/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["webhook_url"])
        self.assertFalse(response.data["webhook_enabled"])

    def test_get_other_users_key_fails(self):
        """Cannot access another user's key."""
        other_user = User.objects.create_user(username="other", password="pass")
        other_org = Organization.objects.create(name="Other Org", slug="other-org")
        Account.objects.create(user=other_user, organization=other_org, email_verified=True)
        other_key = APIKey.objects.create(organization=other_org, name="other-key")

        response = self.client.get(f"/api/v1/auth/tokens/{other_key.id}/webhook/")
        self.assertEqual(response.status_code, 404)

    def test_get_revoked_key_fails(self):
        """Cannot access revoked key."""
        self.key2.revoke()

        response = self.client.get(f"/api/v1/auth/tokens/{self.key2.id}/webhook/")
        self.assertEqual(response.status_code, 404)

    def test_set_url_without_secret_fails(self):
        """Cannot set URL on key without existing secret."""
        response = self.client.put(
            f"/api/v1/auth/tokens/{self.key1.id}/webhook/",
            {"webhook_url": "https://example.com/webhook/"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "NO_SECRET")

    def test_set_url_with_existing_secret(self):
        """Can set URL if key already has secret."""
        # Admin has previously configured this key
        self.key1.webhook_url = "https://old.example.com/webhook/"
        self.key1.generate_webhook_secret()
        self.key1.save()

        response = self.client.put(
            f"/api/v1/auth/tokens/{self.key1.id}/webhook/",
            {"webhook_url": "https://new.example.com/webhook/"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["webhook_url"], "https://new.example.com/webhook/")
        self.assertTrue(response.data["webhook_enabled"])

    def test_copy_secret_from_another_key(self):
        """Can copy webhook config from another key."""
        # key1 has webhook configured
        self.key1.webhook_url = "https://example.com/webhook/"
        self.key1.generate_webhook_secret()
        self.key1.save()
        original_secret = self.key1.webhook_secret

        # Copy to key2
        response = self.client.put(
            f"/api/v1/auth/tokens/{self.key2.id}/webhook/",
            {
                "webhook_url": "https://example.com/webhook/",
                "source_key_id": str(self.key1.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["webhook_secret"], original_secret)
        self.assertTrue(response.data["webhook_enabled"])

    def test_copy_from_key_without_webhook_fails(self):
        """Cannot copy from key that has no webhook."""
        response = self.client.put(
            f"/api/v1/auth/tokens/{self.key2.id}/webhook/",
            {
                "webhook_url": "https://example.com/webhook/",
                "source_key_id": str(self.key1.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "SOURCE_NOT_FOUND")

    def test_copy_from_other_users_key_fails(self):
        """Cannot copy from another user's key."""
        other_user = User.objects.create_user(username="other", password="pass")
        other_org = Organization.objects.create(name="Other Org", slug="other-org-2")
        Account.objects.create(user=other_user, organization=other_org, email_verified=True)
        other_key = APIKey.objects.create(
            organization=other_org,
            name="other-key",
            webhook_url="https://example.com/webhook/",
        )

        response = self.client.put(
            f"/api/v1/auth/tokens/{self.key1.id}/webhook/",
            {
                "webhook_url": "https://example.com/webhook/",
                "source_key_id": str(other_key.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "SOURCE_NOT_FOUND")

    def test_disable_webhook_with_empty_url(self):
        """Can disable webhook by setting empty URL."""
        self.key1.webhook_url = "https://example.com/webhook/"
        self.key1.generate_webhook_secret()
        self.key1.save()

        response = self.client.put(
            f"/api/v1/auth/tokens/{self.key1.id}/webhook/",
            {"webhook_url": ""},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["webhook_url"])
        self.assertFalse(response.data["webhook_enabled"])

    def test_invalid_url_rejected(self):
        """Invalid URL format is rejected."""
        self.key1.generate_webhook_secret()
        self.key1.save()

        response = self.client.put(
            f"/api/v1/auth/tokens/{self.key1.id}/webhook/",
            {"webhook_url": "not-a-url"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "INVALID_URL")
