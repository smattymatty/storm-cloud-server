"""Tests for accounts app utility functions."""

from django.test import TestCase, RequestFactory

from accounts.utils import get_client_ip, send_verification_email
from accounts.tests.factories import UserFactory
from accounts.models import EmailVerificationToken


class GetClientIPTest(TestCase):
    """Tests for get_client_ip utility function."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_extracts_ip_from_x_forwarded_for_header(self):
        """Test IP extraction from X-Forwarded-For header."""
        # request = self.factory.get('/', HTTP_X_FORWARDED_FOR='1.2.3.4, 5.6.7.8')
        # assert get_client_ip(request) == '1.2.3.4'
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8")
        self.assertEqual(get_client_ip(request), "1.2.3.4")

    def test_extracts_ip_from_remote_addr_when_no_forwarded_header(self):
        """Test IP extraction from REMOTE_ADDR."""
        # request = self.factory.get('/')
        # request.META['REMOTE_ADDR'] = '9.8.7.6'
        # assert get_client_ip(request) == '9.8.7.6'
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "9.8.7.6"
        self.assertEqual(get_client_ip(request), "9.8.7.6")

    def test_returns_unknown_when_no_ip_available(self):
        """Test returns 'unknown' when no IP is found."""
        # request = self.factory.get('/')
        # request.META.pop('REMOTE_ADDR', None)
        # assert get_client_ip(request) == 'unknown'
        request = self.factory.get("/")
        request.META.pop("REMOTE_ADDR", None)
        self.assertEqual(get_client_ip(request), "unknown")


class SendVerificationEmailTest(TestCase):
    """Tests for send_verification_email utility function."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = UserFactory(email="test@example.com")

    def test_creates_verification_token(self):
        """Test that a verification token is created."""
        request = self.factory.get("/")
        send_verification_email(self.user, request)
        self.assertTrue(EmailVerificationToken.objects.filter(user=self.user).exists())

    def test_sends_email_to_user(self):
        """Test that email is sent to the user."""
        # from django.core import mail
        # Call send_verification_email
        # assert len(mail.outbox) == 1
        # assert self.user.email in mail.outbox[0].to
        from django.core import mail
        from django.test import override_settings

        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
        ):
            request = self.factory.get("/")
            send_verification_email(self.user, request)
            self.assertEqual(len(mail.outbox), 1)
            self.assertIn(self.user.email, mail.outbox[0].to)

    def test_email_contains_verification_link(self):
        """Test email body contains verification link."""
        from django.core import mail
        from django.test import override_settings

        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
        ):
            request = self.factory.get("/")
            send_verification_email(self.user, request)
            self.assertIn("verify", mail.outbox[0].body.lower())

    def test_token_expires_in_24_hours(self):
        """Test token expiry is set correctly."""
        from django.utils import timezone
        from datetime import timedelta

        request = self.factory.get("/")
        send_verification_email(self.user, request)
        token = EmailVerificationToken.objects.get(user=self.user)
        expected_expiry = timezone.now() + timedelta(hours=24)
        # Allow 5 second tolerance for test execution time
        self.assertAlmostEqual(
            token.expires_at.timestamp(), expected_expiry.timestamp(), delta=5
        )
