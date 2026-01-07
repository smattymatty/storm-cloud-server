"""Tests for webhook configuration endpoints."""

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import APIKey, UserProfile
from django.contrib.auth import get_user_model

User = get_user_model()


class WebhookConfigTests(TestCase):
    """Tests for webhook configuration endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        UserProfile.objects.create(user=self.user, is_email_verified=True)
        self.api_key = APIKey.objects.create(user=self.user, name="test-key")
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
        UserProfile.objects.create(user=self.user, is_email_verified=True)

    def test_secret_generated_on_url_set(self):
        """Secret is auto-generated when URL is set."""
        api_key = APIKey.objects.create(user=self.user, name="test")
        self.assertIsNone(api_key.webhook_secret)

        api_key.webhook_url = "https://example.com/webhook/"
        api_key.save()

        self.assertIsNotNone(api_key.webhook_secret)
        self.assertEqual(len(api_key.webhook_secret), 64)

    def test_secret_cleared_on_url_removed(self):
        """Secret is cleared when URL is removed."""
        api_key = APIKey.objects.create(
            user=self.user, name="test", webhook_url="https://example.com/webhook/"
        )
        self.assertIsNotNone(api_key.webhook_secret)

        api_key.webhook_url = None
        api_key.save()

        self.assertIsNone(api_key.webhook_secret)
        self.assertFalse(api_key.webhook_enabled)

    def test_webhook_enabled_auto_set(self):
        """webhook_enabled is automatically set based on URL presence."""
        api_key = APIKey.objects.create(user=self.user, name="test")
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
            user=self.user, name="test", webhook_url="https://old.example.com/webhook/"
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
        UserProfile.objects.create(user=self.user, is_email_verified=True)
        self.api_key = APIKey.objects.create(user=self.user, name="test-key")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.api_key.key}")

    def test_test_webhook_without_url_fails(self):
        """Can't test webhook without URL configured."""
        response = self.client.post("/api/v1/account/webhook/test/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("No webhook configured", response.data["error"])
