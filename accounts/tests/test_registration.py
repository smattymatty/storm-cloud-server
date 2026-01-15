"""Tests for user registration endpoints."""

from django.test import override_settings
from django.contrib.auth import get_user_model
from rest_framework import status
from unittest.mock import patch

from core.tests.base import StormCloudAPITestCase
from accounts.tests.factories import UserWithProfileFactory
from accounts.models import Account

User = get_user_model()


class RegistrationDisabledTest(StormCloudAPITestCase):
    """Test registration when STORMCLOUD_ALLOW_REGISTRATION=False (default)."""

    def test_registration_returns_403_when_disabled(self):
        """Registration should return 403 when disabled."""
        data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'testpass123',
        }
        response = self.client.post('/api/v1/auth/register/', data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error']['code'], 'REGISTRATION_DISABLED')


@override_settings(STORMCLOUD_ALLOW_REGISTRATION=True)
class RegistrationEnabledTest(StormCloudAPITestCase):
    """Test registration when enabled."""

    def test_registration_creates_user_successfully(self):
        """Successful registration creates user and profile."""
        data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'testpass123',
        }
        response = self.client.post('/api/v1/auth/register/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['user']['username'], 'newuser')
        self.assertTrue(response.data['requires_verification'])

        # Verify user exists
        user = User.objects.get(username='newuser')
        self.assertIsNotNone(user)

        # Verify account was created
        self.assertTrue(Account.objects.filter(user=user).exists())

    def test_registration_sends_verification_email(self):
        """Registration sends verification email."""
        from django.core import mail
        from django.test import override_settings

        with override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            data = {
                'username': 'newuser',
                'email': 'new@example.com',
                'password': 'testpass123',
            }
            response = self.client.post('/api/v1/auth/register/', data)
            self.assertEqual(len(mail.outbox), 1)
            self.assertIn('verify', mail.outbox[0].subject.lower())

    def test_duplicate_username_returns_400(self):
        """Registration with existing username returns validation error."""
        UserWithProfileFactory(username='taken')
        data = {
            'username': 'taken',
            'email': 'new@example.com',
            'password': 'testpass123',
        }
        response = self.client.post('/api/v1/auth/register/', data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_email_returns_400(self):
        """Registration with existing email returns validation error."""
        UserWithProfileFactory(email='taken@example.com')
        data = {
            'username': 'newuser',
            'email': 'taken@example.com',
            'password': 'testpass123',
        }
        response = self.client.post('/api/v1/auth/register/', data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_weak_password_returns_400(self):
        """Registration with weak password returns validation error."""
        data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': '123',
        }
        response = self.client.post('/api/v1/auth/register/', data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_required_fields_returns_400(self):
        """Registration without required fields returns validation error."""
        data = {
            'username': 'newuser',
            'password': 'testpass123',
            # missing email
        }
        response = self.client.post('/api/v1/auth/register/', data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_email_format_returns_400(self):
        """Registration with invalid email format returns validation error."""
        data = {
            'username': 'newuser',
            'email': 'notanemail',
            'password': 'testpass123',
        }
        response = self.client.post('/api/v1/auth/register/', data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_registration_fires_user_registered_signal(self):
        """Registration fires user_registered signal."""
        from accounts.signals import user_registered

        signal_received = []

        def signal_handler(sender, **kwargs):
            signal_received.append(kwargs)

        user_registered.connect(signal_handler)

        data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'testpass123',
        }
        response = self.client.post('/api/v1/auth/register/', data)

        user_registered.disconnect(signal_handler)

        self.assertTrue(len(signal_received) > 0)
