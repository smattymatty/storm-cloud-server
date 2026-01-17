"""Tests for enrollment API endpoints."""

from datetime import timedelta
from django.test import override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status

from core.tests.base import StormCloudAPITestCase
from accounts.tests.factories import (
    UserWithAccountFactory,
    AccountFactory,
    OrganizationFactory,
    EnrollmentKeyFactory,
)
from accounts.models import Account, EnrollmentKey

User = get_user_model()


class EnrollmentValidateTokenTest(StormCloudAPITestCase):
    """Test POST /api/v1/enrollment/validate/"""

    def test_validate_valid_token(self):
        """Valid token returns invite details."""
        org = OrganizationFactory(name="Acme Corp")
        enrollment_key = EnrollmentKeyFactory(organization=org)

        response = self.client.post(
            "/api/v1/enrollment/validate/",
            {
                "token": enrollment_key.key,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["organization_name"], "Acme Corp")
        self.assertEqual(response.data["organization_id"], str(org.id))
        self.assertTrue(response.data["is_valid"])
        self.assertTrue(response.data["single_use"])

    def test_validate_token_with_required_email(self):
        """Token with required_email returns that info."""
        enrollment_key = EnrollmentKeyFactory(required_email="specific@example.com")

        response = self.client.post(
            "/api/v1/enrollment/validate/",
            {
                "token": enrollment_key.key,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["required_email"], "specific@example.com")

    def test_validate_invalid_token(self):
        """Invalid token returns 400."""
        response = self.client.post(
            "/api/v1/enrollment/validate/",
            {
                "token": "ek_invalid_token_12345",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "INVALID_TOKEN")

    def test_validate_expired_token(self):
        """Expired token shows is_valid=False."""
        enrollment_key = EnrollmentKeyFactory(expired=True)

        response = self.client.post(
            "/api/v1/enrollment/validate/",
            {
                "token": enrollment_key.key,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_valid"])

    def test_validate_used_single_use_token(self):
        """Used single-use token shows is_valid=False."""
        account = AccountFactory()
        enrollment_key = EnrollmentKeyFactory(single_use=True)
        enrollment_key.mark_used(account)

        response = self.client.post(
            "/api/v1/enrollment/validate/",
            {
                "token": enrollment_key.key,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_valid"])

    def test_validate_inactive_token(self):
        """Inactive token shows is_valid=False."""
        enrollment_key = EnrollmentKeyFactory(is_active=False)

        response = self.client.post(
            "/api/v1/enrollment/validate/",
            {
                "token": enrollment_key.key,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_valid"])


class EnrollmentEnrollTest(StormCloudAPITestCase):
    """Test POST /api/v1/enrollment/enroll/"""

    def test_enroll_success(self):
        """Successful enrollment creates user and account."""
        org = OrganizationFactory(name="Acme Corp")
        enrollment_key = EnrollmentKeyFactory(organization=org)

        response = self.client.post(
            "/api/v1/enrollment/enroll/",
            {
                "token": enrollment_key.key,
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "securepass123!",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("enrollment_id", response.data)
        self.assertEqual(response.data["email"], "newuser@example.com")

        # Verify user created
        user = User.objects.get(username="newuser")
        self.assertEqual(user.email, "newuser@example.com")

        # Verify account created in correct org
        account = Account.objects.get(user=user)
        self.assertEqual(account.organization, org)
        self.assertFalse(account.is_owner)  # Enrolled users not owners

    def test_enroll_marks_key_as_used(self):
        """Enrollment marks single-use key as used."""
        enrollment_key = EnrollmentKeyFactory(single_use=True)

        response = self.client.post(
            "/api/v1/enrollment/enroll/",
            {
                "token": enrollment_key.key,
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "securepass123!",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Refresh key and check
        enrollment_key.refresh_from_db()
        self.assertEqual(enrollment_key.use_count, 1)
        self.assertIsNotNone(enrollment_key.used_by)
        self.assertFalse(enrollment_key.is_valid())

    def test_enroll_multi_use_key_stays_valid(self):
        """Multi-use key remains valid after use."""
        enrollment_key = EnrollmentKeyFactory(multi_use=True)

        response = self.client.post(
            "/api/v1/enrollment/enroll/",
            {
                "token": enrollment_key.key,
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "securepass123!",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        enrollment_key.refresh_from_db()
        self.assertEqual(enrollment_key.use_count, 1)
        self.assertTrue(enrollment_key.is_valid())

    def test_enroll_with_required_email_match(self):
        """Enrollment succeeds when email matches required_email."""
        enrollment_key = EnrollmentKeyFactory(required_email="specific@example.com")

        response = self.client.post(
            "/api/v1/enrollment/enroll/",
            {
                "token": enrollment_key.key,
                "username": "newuser",
                "email": "specific@example.com",
                "password": "securepass123!",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_enroll_with_required_email_mismatch(self):
        """Enrollment fails when email doesn't match required_email."""
        enrollment_key = EnrollmentKeyFactory(required_email="specific@example.com")

        response = self.client.post(
            "/api/v1/enrollment/enroll/",
            {
                "token": enrollment_key.key,
                "username": "newuser",
                "email": "different@example.com",
                "password": "securepass123!",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_enroll_with_required_email_case_insensitive(self):
        """Email comparison is case-insensitive."""
        enrollment_key = EnrollmentKeyFactory(required_email="Specific@Example.com")

        response = self.client.post(
            "/api/v1/enrollment/enroll/",
            {
                "token": enrollment_key.key,
                "username": "newuser",
                "email": "specific@example.com",
                "password": "securepass123!",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_enroll_invalid_token(self):
        """Enrollment with invalid token fails."""
        response = self.client.post(
            "/api/v1/enrollment/enroll/",
            {
                "token": "ek_invalid_token_12345",
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "securepass123!",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("token", response.data)

    def test_enroll_expired_token(self):
        """Enrollment with expired token fails."""
        enrollment_key = EnrollmentKeyFactory(expired=True)

        response = self.client.post(
            "/api/v1/enrollment/enroll/",
            {
                "token": enrollment_key.key,
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "securepass123!",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("token", response.data)

    def test_enroll_duplicate_username(self):
        """Enrollment with existing username fails."""
        UserWithAccountFactory(username="taken")
        enrollment_key = EnrollmentKeyFactory()

        response = self.client.post(
            "/api/v1/enrollment/enroll/",
            {
                "token": enrollment_key.key,
                "username": "taken",
                "email": "newuser@example.com",
                "password": "securepass123!",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)

    def test_enroll_duplicate_email(self):
        """Enrollment with existing email fails."""
        UserWithAccountFactory(email="taken@example.com")
        enrollment_key = EnrollmentKeyFactory()

        response = self.client.post(
            "/api/v1/enrollment/enroll/",
            {
                "token": enrollment_key.key,
                "username": "newuser",
                "email": "taken@example.com",
                "password": "securepass123!",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_enroll_weak_password(self):
        """Enrollment with weak password fails validation."""
        enrollment_key = EnrollmentKeyFactory()

        response = self.client.post(
            "/api/v1/enrollment/enroll/",
            {
                "token": enrollment_key.key,
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "123",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_enroll_applies_preset_permissions(self):
        """Enrollment applies preset_permissions from key."""
        enrollment_key = EnrollmentKeyFactory(
            preset_permissions={
                "can_upload": False,
                "can_delete": False,
                "storage_quota_bytes": 1000000,
            }
        )

        response = self.client.post(
            "/api/v1/enrollment/enroll/",
            {
                "token": enrollment_key.key,
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "securepass123!",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        account = Account.objects.get(id=response.data["enrollment_id"])
        self.assertFalse(account.can_upload)
        self.assertFalse(account.can_delete)
        self.assertEqual(account.storage_quota_bytes, 1000000)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_enroll_sends_verification_email(self):
        """Enrollment sends verification email when required."""
        from django.core import mail

        enrollment_key = EnrollmentKeyFactory()

        response = self.client.post(
            "/api/v1/enrollment/enroll/",
            {
                "token": enrollment_key.key,
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "securepass123!",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("verify", mail.outbox[0].subject.lower())

    def test_enroll_fires_user_registered_signal(self):
        """Enrollment fires user_registered signal."""
        from accounts.signals import user_registered

        signal_received = []

        def signal_handler(sender, **kwargs):
            signal_received.append(kwargs)

        user_registered.connect(signal_handler)

        enrollment_key = EnrollmentKeyFactory()

        response = self.client.post(
            "/api/v1/enrollment/enroll/",
            {
                "token": enrollment_key.key,
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "securepass123!",
            },
        )

        user_registered.disconnect(signal_handler)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(signal_received), 1)


class EnrollmentStatusTest(StormCloudAPITestCase):
    """Test GET /api/v1/enrollment/status/{enrollment_id}/"""

    def test_status_unverified(self):
        """Status shows unverified account correctly."""
        account = AccountFactory(email_verified=False)

        response = self.client.get(f"/api/v1/enrollment/status/{account.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["email_verified"])
        self.assertFalse(response.data["can_login"])
        self.assertEqual(response.data["username"], account.user.username)

    def test_status_verified(self):
        """Status shows verified account correctly."""
        account = AccountFactory(email_verified=True, is_active=True)

        response = self.client.get(f"/api/v1/enrollment/status/{account.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["email_verified"])
        self.assertTrue(response.data["can_login"])

    def test_status_verified_but_inactive(self):
        """Verified but inactive account cannot login."""
        account = AccountFactory(email_verified=True, is_active=False)

        response = self.client.get(f"/api/v1/enrollment/status/{account.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["email_verified"])
        self.assertFalse(response.data["can_login"])

    def test_status_not_found(self):
        """Status for non-existent enrollment returns 404."""
        import uuid

        fake_id = uuid.uuid4()

        response = self.client.get(f"/api/v1/enrollment/status/{fake_id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class EnrollmentResendTest(StormCloudAPITestCase):
    """Test POST /api/v1/enrollment/resend/{enrollment_id}/"""

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_resend_success(self):
        """Resend verification email for unverified account."""
        from django.core import mail

        account = AccountFactory(email_verified=False)

        response = self.client.post(f"/api/v1/enrollment/resend/{account.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)
        self.assertEqual(len(mail.outbox), 1)

    def test_resend_already_verified(self):
        """Resend fails for already verified account."""
        account = AccountFactory(email_verified=True)

        response = self.client.post(f"/api/v1/enrollment/resend/{account.id}/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "ALREADY_VERIFIED")

    def test_resend_not_found(self):
        """Resend for non-existent enrollment returns 404."""
        import uuid

        fake_id = uuid.uuid4()

        response = self.client.post(f"/api/v1/enrollment/resend/{fake_id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class EnrollmentInviteCreateTest(StormCloudAPITestCase):
    """Test POST /api/v1/enrollment/invite/create/"""

    def test_create_invite_success(self):
        """User with can_invite can create invites."""
        # Give user can_invite permission
        self.user.account.can_invite = True
        self.user.account.save()

        self.authenticate()

        response = self.client.post(
            "/api/v1/enrollment/invite/create/",
            {
                "expiry_days": 7,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("token", response.data)
        self.assertIn("expires_at", response.data)
        self.assertTrue(response.data["single_use"])
        self.assertFalse(response.data["email_sent"])  # No email provided

        # Verify key was created
        key = EnrollmentKey.objects.get(key=response.data["token"])
        self.assertEqual(key.organization, self.user.account.organization)
        self.assertEqual(key.created_by, self.user.account)

    def test_create_invite_with_email(self):
        """Invite can be restricted to specific email."""
        self.user.account.can_invite = True
        self.user.account.save()

        self.authenticate()

        response = self.client.post(
            "/api/v1/enrollment/invite/create/",
            {
                "email": "specific@example.com",
                "expiry_days": 14,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["required_email"], "specific@example.com")

    def test_create_invite_multi_use(self):
        """Can create multi-use invite."""
        self.user.account.can_invite = True
        self.user.account.save()

        self.authenticate()

        response = self.client.post(
            "/api/v1/enrollment/invite/create/",
            {
                "expiry_days": 7,
                "single_use": False,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data["single_use"])

    def test_create_invite_with_name(self):
        """Invite can have custom name."""
        self.user.account.can_invite = True
        self.user.account.save()

        self.authenticate()

        response = self.client.post(
            "/api/v1/enrollment/invite/create/",
            {
                "expiry_days": 7,
                "name": "Sales Team Invite",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        key = EnrollmentKey.objects.get(key=response.data["token"])
        self.assertEqual(key.name, "Sales Team Invite")

    def test_create_invite_permission_denied(self):
        """User without can_invite cannot create invites."""
        # Ensure user does not have can_invite
        self.user.account.can_invite = False
        self.user.account.save()

        self.authenticate()

        response = self.client.post(
            "/api/v1/enrollment/invite/create/",
            {
                "expiry_days": 7,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["error"]["code"], "PERMISSION_DENIED")
        self.assertEqual(response.data["error"]["permission"], "can_invite")

    def test_create_invite_requires_auth(self):
        """Create invite requires authentication."""
        # No authentication
        response = self.client.post(
            "/api/v1/enrollment/invite/create/",
            {
                "expiry_days": 7,
            },
        )

        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_create_invite_validates_expiry_range(self):
        """Expiry days must be 1-365."""
        self.user.account.can_invite = True
        self.user.account.save()

        self.authenticate()

        # Too low
        response = self.client.post(
            "/api/v1/enrollment/invite/create/",
            {
                "expiry_days": 0,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Too high
        response = self.client.post(
            "/api/v1/enrollment/invite/create/",
            {
                "expiry_days": 400,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_invite_send_email_false(self):
        """Can disable email sending."""
        self.user.account.can_invite = True
        self.user.account.save()

        self.authenticate()

        response = self.client.post(
            "/api/v1/enrollment/invite/create/",
            {
                "email": "test@example.com",
                "expiry_days": 7,
                "send_email": False,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data["email_sent"])

    def test_create_invite_email_sent_on_success(self):
        """Email is marked as sent when email sending succeeds."""
        self.user.account.can_invite = True
        self.user.account.save()

        self.authenticate()

        # With console backend, email "sending" won't raise an exception
        response = self.client.post(
            "/api/v1/enrollment/invite/create/",
            {
                "email": "test@example.com",
                "expiry_days": 7,
                "send_email": True,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # email_sent will be True because console backend doesn't fail
        self.assertTrue(response.data["email_sent"])


class EnrollmentValidateEmailFieldsTest(StormCloudAPITestCase):
    """Test email and email_editable fields in validate response."""

    def test_validate_returns_email_fields_when_preset(self):
        """When email is preset by admin, email_editable is False."""
        enrollment_key = EnrollmentKeyFactory(required_email="preset@example.com")

        response = self.client.post(
            "/api/v1/enrollment/validate/",
            {
                "token": enrollment_key.key,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "preset@example.com")
        self.assertFalse(response.data["email_editable"])

    def test_validate_returns_editable_when_no_email(self):
        """When no email preset, email_editable is True."""
        enrollment_key = EnrollmentKeyFactory(required_email=None)

        response = self.client.post(
            "/api/v1/enrollment/validate/",
            {
                "token": enrollment_key.key,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["email"])
        self.assertTrue(response.data["email_editable"])


class EmailStatusTest(StormCloudAPITestCase):
    """Test GET /api/v1/enrollment/email-status/"""

    def test_email_status_requires_auth(self):
        """Email status endpoint requires authentication."""
        response = self.client.get("/api/v1/enrollment/email-status/")

        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
        EMAIL_HOST="",
    )
    def test_email_status_returns_not_configured(self):
        """Email status returns False when using console backend."""
        self.authenticate()

        response = self.client.get("/api/v1/enrollment/email-status/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("configured", response.data)
        self.assertFalse(response.data["configured"])

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="smtp.example.com",
    )
    def test_email_status_returns_configured(self):
        """Email status returns True when email is configured."""
        self.authenticate()

        response = self.client.get("/api/v1/enrollment/email-status/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("configured", response.data)
        self.assertTrue(response.data["configured"])
