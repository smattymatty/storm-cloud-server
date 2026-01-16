"""Tests for email verification endpoints."""

from django.test import override_settings
from rest_framework import status

from core.tests.base import StormCloudAPITestCase
from accounts.tests.factories import (
    UserWithProfileFactory,
    EmailVerificationTokenFactory,
)
from accounts.models import EmailVerificationToken


class EmailVerificationTest(StormCloudAPITestCase):
    """Tests for POST /api/v1/auth/verify-email/"""

    def test_verify_email_with_valid_token_succeeds(self):
        """Verification with valid token marks email as verified."""
        user = UserWithProfileFactory()
        token = EmailVerificationTokenFactory(user=user)

        response = self.client.post(
            "/api/v1/auth/verify-email/", {"token": token.token}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        user.account.refresh_from_db()
        self.assertTrue(user.account.email_verified)

    def test_verify_email_with_invalid_token_returns_400(self):
        """Verification with non-existent token returns error."""
        response = self.client.post(
            "/api/v1/auth/verify-email/", {"token": "invalidtoken123"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "INVALID_TOKEN")

    def test_verify_email_with_expired_token_returns_400(self):
        """Verification with expired token returns error."""
        user = UserWithProfileFactory()
        token = EmailVerificationTokenFactory(user=user, expired=True)

        response = self.client.post(
            "/api/v1/auth/verify-email/", {"token": token.token}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "TOKEN_EXPIRED")

    def test_verify_email_with_already_used_token_returns_400(self):
        """Verification with used token returns error."""
        user = UserWithProfileFactory()
        token = EmailVerificationTokenFactory(user=user, used=True)

        response = self.client.post(
            "/api/v1/auth/verify-email/", {"token": token.token}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "ALREADY_VERIFIED")

    def test_verify_email_marks_token_as_used(self):
        """Successful verification marks token as used."""
        user = UserWithProfileFactory()
        token = EmailVerificationTokenFactory(user=user)

        response = self.client.post(
            "/api/v1/auth/verify-email/", {"token": token.token}
        )

        token.refresh_from_db()
        self.assertIsNotNone(token.used_at)

    def test_verify_email_fires_email_verified_signal(self):
        """Successful verification fires email_verified signal."""
        from accounts.signals import email_verified

        signal_received = []

        def signal_handler(sender, **kwargs):
            signal_received.append(kwargs)

        email_verified.connect(signal_handler)

        user = UserWithProfileFactory()
        token = EmailVerificationTokenFactory(user=user)
        response = self.client.post(
            "/api/v1/auth/verify-email/", {"token": token.token}
        )

        email_verified.disconnect(signal_handler)

        self.assertTrue(len(signal_received) > 0)


class ResendVerificationTest(StormCloudAPITestCase):
    """Tests for POST /api/v1/auth/resend-verification/"""

    def test_resend_for_existing_unverified_user_sends_email(self):
        """Resending for unverified user sends email."""
        from django.core import mail

        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
        ):
            user = UserWithProfileFactory()
            response = self.client.post(
                "/api/v1/auth/resend-verification/", {"email": user.email}
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(mail.outbox), 1)

    def test_resend_for_verified_user_does_not_send_email(self):
        """Resending for already verified user doesn't send email."""
        from django.core import mail

        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
        ):
            user = UserWithProfileFactory(verified=True)
            response = self.client.post(
                "/api/v1/auth/resend-verification/", {"email": user.email}
            )
            self.assertEqual(len(mail.outbox), 0)

    def test_resend_for_nonexistent_email_returns_success(self):
        """Resending for non-existent email returns success (anti-enumeration)."""
        response = self.client.post(
            "/api/v1/auth/resend-verification/", {"email": "doesnotexist@example.com"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)

    def test_resend_creates_new_token(self):
        """Resending creates a new verification token."""
        user = UserWithProfileFactory()
        before_count = EmailVerificationToken.objects.filter(user=user).count()

        response = self.client.post(
            "/api/v1/auth/resend-verification/", {"email": user.email}
        )

        after_count = EmailVerificationToken.objects.filter(user=user).count()
        self.assertGreater(after_count, before_count)
