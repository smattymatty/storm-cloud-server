"""Tests for accounts app signals."""

from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from unittest.mock import patch, MagicMock

from accounts.signals import (
    user_registered,
    email_verified,
    api_key_created,
    api_key_revoked,
    account_deactivated,
    account_deleted,
    login_failed,
)
from accounts.tests.factories import UserFactory, APIKeyFactory

User = get_user_model()


class UserRegisteredSignalTest(TestCase):
    """Tests for user_registered signal."""

    @patch('accounts.signal_handlers.security_logger')
    def test_signal_logs_user_registration(self, mock_logger):
        """Test user_registered signal triggers security logging."""
        # factory = RequestFactory()
        # request = factory.post('/')
        # user = UserFactory()
        # user_registered.send(sender=User, user=user, request=request)
        # assert mock_logger.info.called
        factory = RequestFactory()
        request = factory.post('/')
        user = UserFactory()
        user_registered.send(sender=User, user=user, request=request)
        self.assertTrue(mock_logger.info.called)


class EmailVerifiedSignalTest(TestCase):
    """Tests for email_verified signal."""

    @patch('accounts.signal_handlers.security_logger')
    def test_signal_logs_email_verification(self, mock_logger):
        """Test email_verified signal triggers security logging."""
        # user = UserFactory()
        # email_verified.send(sender=User, user=user)
        # assert mock_logger.info.called
        user = UserFactory()
        email_verified.send(sender=User, user=user)
        self.assertTrue(mock_logger.info.called)


class APIKeyCreatedSignalTest(TestCase):
    """Tests for api_key_created signal."""

    @patch('accounts.signal_handlers.security_logger')
    def test_signal_logs_api_key_creation(self, mock_logger):
        """Test api_key_created signal triggers security logging."""
        # user = UserFactory()
        # api_key = APIKeyFactory(user=user)
        # api_key_created.send(sender=type(api_key), api_key=api_key, user=user)
        # assert mock_logger.info.called
        user = UserFactory()
        api_key = APIKeyFactory(user=user)
        api_key_created.send(sender=type(api_key), api_key=api_key, user=user)
        self.assertTrue(mock_logger.info.called)


class APIKeyRevokedSignalTest(TestCase):
    """Tests for api_key_revoked signal."""

    @patch('accounts.signal_handlers.security_logger')
    def test_signal_logs_api_key_revocation(self, mock_logger):
        """Test api_key_revoked signal triggers security logging."""
        user = UserFactory()
        api_key = APIKeyFactory(user=user, revoked=True)
        api_key_revoked.send(sender=type(api_key), api_key=api_key, user=user, revoked_by=user)
        self.assertTrue(mock_logger.info.called)


class AccountDeactivatedSignalTest(TestCase):
    """Tests for account_deactivated signal."""

    @patch('accounts.signal_handlers.security_logger')
    def test_signal_logs_account_deactivation(self, mock_logger):
        """Test account_deactivated signal triggers security logging."""
        user = UserFactory()
        account_deactivated.send(sender=User, user=user)
        self.assertTrue(mock_logger.warning.called)


class AccountDeletedSignalTest(TestCase):
    """Tests for account_deleted signal."""

    @patch('accounts.signal_handlers.security_logger')
    def test_signal_logs_account_deletion(self, mock_logger):
        """Test account_deleted signal triggers security logging."""
        account_deleted.send(sender=User, user_id=123, username='deleteduser')
        self.assertTrue(mock_logger.warning.called)


class LoginFailedSignalTest(TestCase):
    """Tests for login_failed signal."""

    @patch('accounts.signal_handlers.security_logger')
    def test_signal_logs_failed_login(self, mock_logger):
        """Test login_failed signal triggers security logging."""
        login_failed.send(sender=User, username='baduser', ip_address='1.2.3.4', reason='Invalid credentials')
        self.assertTrue(mock_logger.warning.called)
