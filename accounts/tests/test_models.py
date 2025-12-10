"""Tests for accounts app models."""

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from accounts.tests.factories import (
    UserFactory,
    UserProfileFactory,
    APIKeyFactory,
    EmailVerificationTokenFactory,
)


class UserProfileModelTest(TestCase):
    """Tests for UserProfile model."""

    def test_string_representation(self):
        """Test __str__ method."""
        user = UserFactory(username='testuser')
        profile = UserProfileFactory(user=user)
        self.assertEqual(str(profile), f"Profile: {user.username}")

    def test_profile_created_with_user(self):
        """Test profile can be created for a user."""
        user = UserFactory()
        profile = UserProfileFactory(user=user)
        self.assertEqual(profile.user, user)
        self.assertTrue(profile.id is not None)

    def test_default_is_email_verified_is_false(self):
        """Test new profiles default to unverified."""
        profile = UserProfileFactory()
        self.assertEqual(profile.is_email_verified, False)


class EmailVerificationTokenModelTest(TestCase):
    """Tests for EmailVerificationToken model."""

    def test_string_representation(self):
        """Test __str__ method shows status."""
        user = UserFactory(username='testuser')
        token = EmailVerificationTokenFactory(user=user)
        self.assertIn(user.username, str(token))
        self.assertIn('pending', str(token).lower())

        token.mark_used()
        self.assertIn('used', str(token).lower())

    def test_is_expired_property_with_expired_token(self):
        """Test is_expired returns True for expired tokens."""
        token = EmailVerificationTokenFactory(expired=True)
        self.assertTrue(token.is_expired)

    def test_is_expired_property_with_valid_token(self):
        """Test is_expired returns False for valid tokens."""
        token = EmailVerificationTokenFactory()
        self.assertFalse(token.is_expired)

    def test_is_valid_property_with_expired_token(self):
        """Test is_valid returns False for expired tokens."""
        token = EmailVerificationTokenFactory(expired=True)
        self.assertFalse(token.is_valid)

    def test_is_valid_property_with_used_token(self):
        """Test is_valid returns False for used tokens."""
        token = EmailVerificationTokenFactory(used=True)
        self.assertFalse(token.is_valid)

    def test_is_valid_property_with_valid_token(self):
        """Test is_valid returns True for valid unused tokens."""
        token = EmailVerificationTokenFactory()
        self.assertTrue(token.is_valid)

    def test_mark_used_sets_used_at_timestamp(self):
        """Test mark_used() sets used_at to current time."""
        token = EmailVerificationTokenFactory()
        self.assertIsNone(token.used_at)
        token.mark_used()
        self.assertIsNotNone(token.used_at)

    def test_token_is_generated_automatically(self):
        """Test token field is auto-generated."""
        token = EmailVerificationTokenFactory()
        self.assertIsNotNone(token.token)
        self.assertGreater(len(token.token), 0)


class APIKeyModelTest(TestCase):
    """Tests for APIKey model."""

    def test_string_representation(self):
        """Test __str__ method includes name and username."""
        user = UserFactory(username='testuser')
        api_key = APIKeyFactory(user=user, name='test-key')
        self.assertIn('test-key', str(api_key))
        self.assertIn('testuser', str(api_key))

    def test_key_is_generated_on_creation(self):
        """Test API key is auto-generated on save."""
        api_key = APIKeyFactory()
        self.assertIsNotNone(api_key.key)
        self.assertGreater(len(api_key.key), 0)

    def test_revoke_method_sets_is_active_false(self):
        """Test revoke() sets is_active to False."""
        api_key = APIKeyFactory(is_active=True)
        self.assertTrue(api_key.is_active)
        api_key.revoke()
        self.assertFalse(api_key.is_active)

    def test_revoke_method_sets_revoked_at_timestamp(self):
        """Test revoke() sets revoked_at to current time."""
        api_key = APIKeyFactory()
        self.assertIsNone(api_key.revoked_at)
        api_key.revoke()
        self.assertIsNotNone(api_key.revoked_at)

    def test_default_scope_is_empty_list(self):
        """Test scope defaults to empty list."""
        api_key = APIKeyFactory()
        self.assertEqual(api_key.scope, [])
