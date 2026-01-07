"""Tests for webhook triggering on file operations."""

from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model

from accounts.models import APIKey, UserProfile
from accounts.services.webhook import trigger_webhook, _deliver_webhook

User = get_user_model()


class WebhookTriggerTests(TestCase):
    """Tests for webhook trigger service."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass"
        )
        UserProfile.objects.create(user=self.user, is_email_verified=True)
        self.api_key = APIKey.objects.create(
            user=self.user,
            name="test-key",
            webhook_url="https://example.com/webhook/",
        )

    def test_trigger_does_nothing_without_webhook(self):
        """No webhook configured = no action."""
        api_key = APIKey.objects.create(user=self.user, name="no-webhook")

        with patch("accounts.services.webhook.threading.Thread") as mock_thread:
            trigger_webhook(api_key, "file.updated", "test.md")
            mock_thread.assert_not_called()

    def test_trigger_does_nothing_when_disabled(self):
        """Webhook disabled = no action."""
        self.api_key.webhook_enabled = False
        self.api_key.save()

        with patch("accounts.services.webhook.threading.Thread") as mock_thread:
            trigger_webhook(self.api_key, "file.updated", "test.md")
            mock_thread.assert_not_called()

    def test_trigger_starts_background_thread(self):
        """Webhook triggers in background thread."""
        with patch("accounts.services.webhook.threading.Thread") as mock_thread:
            mock_instance = MagicMock()
            mock_thread.return_value = mock_instance

            trigger_webhook(self.api_key, "file.updated", "pages/about.md")

            mock_thread.assert_called_once()
            mock_instance.start.assert_called_once()

    @patch("accounts.services.webhook.requests.post")
    def test_deliver_webhook_success(self, mock_post):
        """Successful webhook delivery updates status."""
        mock_post.return_value.ok = True
        mock_post.return_value.status_code = 200

        _deliver_webhook(self.api_key.id, "file.updated", "pages/about.md")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args

        # Check URL
        self.assertEqual(call_kwargs[0][0], "https://example.com/webhook/")

        # Check headers
        headers = call_kwargs[1]["headers"]
        self.assertEqual(headers["X-Storm-Event"], "file.updated")
        self.assertIn("X-Storm-Signature", headers)
        self.assertEqual(headers["Content-Type"], "application/json")

        # Check payload
        payload = call_kwargs[1]["json"]
        self.assertEqual(payload["event"], "file.updated")
        self.assertEqual(payload["path"], "pages/about.md")
        self.assertIn("timestamp", payload)
        self.assertEqual(payload["api_key_id"], str(self.api_key.id))

        # Check status updated
        self.api_key.refresh_from_db()
        self.assertEqual(self.api_key.webhook_last_status, "success")
        self.assertIsNotNone(self.api_key.webhook_last_triggered)

    @patch("accounts.services.webhook.requests.post")
    def test_deliver_webhook_failure(self, mock_post):
        """Failed webhook updates status."""
        mock_post.return_value.ok = False
        mock_post.return_value.status_code = 500

        _deliver_webhook(self.api_key.id, "file.updated", "pages/about.md")

        self.api_key.refresh_from_db()
        self.assertEqual(self.api_key.webhook_last_status, "failed")
        self.assertIsNotNone(self.api_key.webhook_last_triggered)

    @patch("accounts.services.webhook.requests.post")
    def test_deliver_webhook_timeout(self, mock_post):
        """Timeout updates status."""
        import requests
        mock_post.side_effect = requests.Timeout()

        _deliver_webhook(self.api_key.id, "file.updated", "pages/about.md")

        self.api_key.refresh_from_db()
        self.assertEqual(self.api_key.webhook_last_status, "timeout")
        self.assertIsNotNone(self.api_key.webhook_last_triggered)

    @patch("accounts.services.webhook.requests.post")
    def test_deliver_webhook_connection_error(self, mock_post):
        """Connection error updates status."""
        import requests
        mock_post.side_effect = requests.ConnectionError()

        _deliver_webhook(self.api_key.id, "file.updated", "pages/about.md")

        self.api_key.refresh_from_db()
        self.assertEqual(self.api_key.webhook_last_status, "failed")
        self.assertIsNotNone(self.api_key.webhook_last_triggered)

    @patch("accounts.services.webhook.requests.post")
    def test_signature_is_valid_hmac(self, mock_post):
        """Signature is valid HMAC-SHA256."""
        import hashlib
        import hmac
        import json

        mock_post.return_value.ok = True

        _deliver_webhook(self.api_key.id, "file.updated", "pages/about.md")

        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"]
        signature = call_kwargs[1]["headers"]["X-Storm-Signature"]

        # Verify signature
        payload_bytes = json.dumps(payload, sort_keys=True).encode()
        expected = hmac.new(
            self.api_key.webhook_secret.encode(),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()

        self.assertEqual(signature, expected)

    @patch("accounts.services.webhook.requests.post")
    def test_extra_data_included(self, mock_post):
        """Extra data is merged into payload."""
        mock_post.return_value.ok = True

        _deliver_webhook(
            self.api_key.id,
            "file.moved",
            "new/path.md",
            extra_data={"old_path": "old/path.md"}
        )

        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["path"], "new/path.md")
        self.assertEqual(payload["old_path"], "old/path.md")
        self.assertEqual(payload["event"], "file.moved")

    def test_deliver_webhook_missing_api_key(self):
        """Delivery fails gracefully for missing API key."""
        import uuid
        # Should not raise, just log warning
        _deliver_webhook(uuid.uuid4(), "file.updated", "test.md")

    @patch("accounts.services.webhook.requests.post")
    def test_deliver_skips_disabled_webhook(self, mock_post):
        """Delivery skips if webhook disabled between trigger and delivery."""
        self.api_key.webhook_enabled = False
        self.api_key.save()

        _deliver_webhook(self.api_key.id, "file.updated", "test.md")

        mock_post.assert_not_called()

    @patch("accounts.services.webhook.requests.post")
    def test_deliver_skips_removed_url(self, mock_post):
        """Delivery skips if webhook URL removed between trigger and delivery."""
        self.api_key.webhook_url = None
        self.api_key.webhook_enabled = False
        self.api_key.save()

        _deliver_webhook(self.api_key.id, "file.updated", "test.md")

        mock_post.assert_not_called()


class WebhookEventTypesTests(TestCase):
    """Tests for different webhook event types."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass"
        )
        UserProfile.objects.create(user=self.user, is_email_verified=True)
        self.api_key = APIKey.objects.create(
            user=self.user,
            name="test-key",
            webhook_url="https://example.com/webhook/",
        )

    @patch("accounts.services.webhook.requests.post")
    def test_file_created_event(self, mock_post):
        """file.created event is sent correctly."""
        mock_post.return_value.ok = True

        _deliver_webhook(self.api_key.id, "file.created", "new-file.md")

        payload = mock_post.call_args[1]["json"]
        headers = mock_post.call_args[1]["headers"]
        self.assertEqual(payload["event"], "file.created")
        self.assertEqual(headers["X-Storm-Event"], "file.created")

    @patch("accounts.services.webhook.requests.post")
    def test_file_updated_event(self, mock_post):
        """file.updated event is sent correctly."""
        mock_post.return_value.ok = True

        _deliver_webhook(self.api_key.id, "file.updated", "existing.md")

        payload = mock_post.call_args[1]["json"]
        headers = mock_post.call_args[1]["headers"]
        self.assertEqual(payload["event"], "file.updated")
        self.assertEqual(headers["X-Storm-Event"], "file.updated")

    @patch("accounts.services.webhook.requests.post")
    def test_file_deleted_event(self, mock_post):
        """file.deleted event is sent correctly."""
        mock_post.return_value.ok = True

        _deliver_webhook(self.api_key.id, "file.deleted", "removed.md")

        payload = mock_post.call_args[1]["json"]
        headers = mock_post.call_args[1]["headers"]
        self.assertEqual(payload["event"], "file.deleted")
        self.assertEqual(headers["X-Storm-Event"], "file.deleted")

    @patch("accounts.services.webhook.requests.post")
    def test_file_moved_event(self, mock_post):
        """file.moved event is sent correctly with old_path."""
        mock_post.return_value.ok = True

        _deliver_webhook(
            self.api_key.id,
            "file.moved",
            "new/location.md",
            extra_data={"old_path": "old/location.md"}
        )

        payload = mock_post.call_args[1]["json"]
        headers = mock_post.call_args[1]["headers"]
        self.assertEqual(payload["event"], "file.moved")
        self.assertEqual(payload["path"], "new/location.md")
        self.assertEqual(payload["old_path"], "old/location.md")
        self.assertEqual(headers["X-Storm-Event"], "file.moved")
