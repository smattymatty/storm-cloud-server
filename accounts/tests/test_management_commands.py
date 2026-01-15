"""Tests for management commands."""

from io import StringIO
from django.core.management import call_command
from django.test import TestCase
from django.contrib.auth import get_user_model
from accounts.models import APIKey
from accounts.tests.factories import UserWithProfileFactory, APIKeyFactory

User = get_user_model()


class CreateTestUserCommandTest(TestCase):
    """Tests for create_test_user management command."""

    def test_creates_basic_user(self):
        """Create test user should work."""
        out = StringIO()
        call_command('create_test_user', '--username', 'testuser', stdout=out)
        self.assertTrue(User.objects.filter(username='testuser').exists())

    def test_creates_verified_user(self):
        """Create test user with --verified should work."""
        out = StringIO()
        call_command('create_test_user', '--username', 'testuser', '--verified', stdout=out)
        user = User.objects.get(username='testuser')
        self.assertTrue(user.account.email_verified)


class GenerateAPIKeyCommandTest(TestCase):
    """Tests for generate_api_key management command."""

    def setUp(self):
        self.user = UserWithProfileFactory(username='testuser')

    def test_generates_key_for_user(self):
        """Generate API key should work."""
        out = StringIO()
        call_command('generate_api_key', 'testuser', '--name', 'test-key', stdout=out)
        self.assertTrue(APIKey.objects.filter(organization=self.user.account.organization, name='test-key').exists())


class RevokeAPIKeyCommandTest(TestCase):
    """Tests for revoke_api_key management command."""

    def setUp(self):
        self.user = UserWithProfileFactory(username='testuser')
        self.key = APIKeyFactory(user=self.user, name='to-revoke')

    def test_revokes_key_by_id(self):
        """Revoke API key by ID should work."""
        out = StringIO()
        call_command('revoke_api_key', str(self.key.id), stdout=out)
        self.key.refresh_from_db()
        self.assertFalse(self.key.is_active)
