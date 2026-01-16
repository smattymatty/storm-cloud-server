"""Tests for admin invite management endpoints."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.admin_invite_api import get_invite_status
from accounts.models import EnrollmentKey, PlatformInvite
from accounts.tests.factories import (
    AccountFactory,
    APIKeyFactory,
    EnrollmentKeyFactory,
    OrganizationFactory,
    PlatformInviteFactory,
    UserWithAccountFactory,
)


class InviteStatusDerivationTest(TestCase):
    """Unit tests for get_invite_status() function."""

    def test_status_pending(self):
        """Fresh invite returns 'pending'."""
        ek = EnrollmentKeyFactory()
        self.assertEqual(get_invite_status(ek), 'pending')

    def test_status_accepted_enrollment_key(self):
        """EnrollmentKey with used_by set returns 'accepted'."""
        account = AccountFactory()
        ek = EnrollmentKeyFactory(used_by=account)
        self.assertEqual(get_invite_status(ek), 'accepted')

    def test_status_accepted_platform_invite(self):
        """PlatformInvite with is_used=True returns 'accepted'."""
        pi = PlatformInviteFactory(used=True)
        self.assertEqual(get_invite_status(pi), 'accepted')

    def test_status_revoked_by_flag(self):
        """is_active=False returns 'revoked'."""
        ek = EnrollmentKeyFactory(is_active=False)
        self.assertEqual(get_invite_status(ek), 'revoked')

    def test_status_revoked_by_timestamp(self):
        """revoked_at set returns 'revoked'."""
        ek = EnrollmentKeyFactory()
        ek.revoked_at = timezone.now()
        ek.save()
        self.assertEqual(get_invite_status(ek), 'revoked')

    def test_status_expired(self):
        """expires_at in past returns 'expired'."""
        ek = EnrollmentKeyFactory(expired=True)
        self.assertEqual(get_invite_status(ek), 'expired')

    def test_status_priority_accepted_over_revoked(self):
        """Accepted takes precedence over revoked."""
        account = AccountFactory()
        ek = EnrollmentKeyFactory(used_by=account, is_active=False)
        self.assertEqual(get_invite_status(ek), 'accepted')

    def test_status_priority_accepted_over_expired(self):
        """Accepted takes precedence over expired."""
        account = AccountFactory()
        ek = EnrollmentKeyFactory(
            used_by=account,
            expires_at=timezone.now() - timedelta(days=1)
        )
        self.assertEqual(get_invite_status(ek), 'accepted')


class AdminInviteListTest(TestCase):
    """Tests for GET /api/v1/admin/invites/"""

    def setUp(self):
        self.client = APIClient()
        self.url = '/api/v1/admin/invites/'

    def test_list_invites_as_platform_admin(self):
        """Platform admin sees all invites (org + platform)."""
        admin = UserWithAccountFactory(admin=True)

        # Create invites in different orgs
        org1 = OrganizationFactory()
        org2 = OrganizationFactory()
        ek1 = EnrollmentKeyFactory(organization=org1)
        ek2 = EnrollmentKeyFactory(organization=org2)
        pi = PlatformInviteFactory()

        self.client.force_login(admin)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)

        # Verify both types are included
        types = [r['type'] for r in response.data['results']]
        self.assertIn('org', types)
        self.assertIn('platform', types)

    def test_list_invites_as_org_admin(self):
        """Org admin only sees their org's invites."""
        # Create org admin
        org = OrganizationFactory()
        user = UserWithAccountFactory(verified=True)
        user.account.organization = org
        user.account.can_invite = True
        user.account.save()

        # Create invites
        ek_own = EnrollmentKeyFactory(organization=org)
        other_org = OrganizationFactory()
        ek_other = EnrollmentKeyFactory(organization=other_org)
        pi = PlatformInviteFactory()

        self.client.force_login(user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(str(response.data['results'][0]['id']), str(ek_own.id))

    def test_list_invites_filter_by_status(self):
        """Filter by pending/accepted/expired/revoked."""
        admin = UserWithAccountFactory(admin=True)
        account = AccountFactory()

        # Create invites with different statuses
        pending = EnrollmentKeyFactory()
        accepted = EnrollmentKeyFactory(used_by=account)
        expired = EnrollmentKeyFactory(expired=True)
        revoked = EnrollmentKeyFactory(is_active=False)

        self.client.force_login(admin)

        # Filter pending
        response = self.client.get(f'{self.url}?status=pending')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['status'], 'pending')

        # Filter accepted
        response = self.client.get(f'{self.url}?status=accepted')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['status'], 'accepted')

        # Filter expired
        response = self.client.get(f'{self.url}?status=expired')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['status'], 'expired')

        # Filter revoked
        response = self.client.get(f'{self.url}?status=revoked')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['status'], 'revoked')

    def test_list_invites_filter_by_type(self):
        """Filter by org/platform."""
        admin = UserWithAccountFactory(admin=True)

        ek = EnrollmentKeyFactory()
        pi = PlatformInviteFactory()

        self.client.force_login(admin)

        # Filter org
        response = self.client.get(f'{self.url}?type=org')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['type'], 'org')

        # Filter platform
        response = self.client.get(f'{self.url}?type=platform')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['type'], 'platform')

    def test_list_invites_pagination(self):
        """Pagination with page/page_size params."""
        admin = UserWithAccountFactory(admin=True)

        # Create 5 invites
        for _ in range(5):
            EnrollmentKeyFactory()

        self.client.force_login(admin)

        # Page 1 with page_size=2
        response = self.client.get(f'{self.url}?page=1&page_size=2')
        self.assertEqual(response.data['count'], 5)
        self.assertEqual(len(response.data['results']), 2)
        self.assertIsNotNone(response.data['next'])
        self.assertIsNone(response.data['previous'])

        # Page 2
        response = self.client.get(f'{self.url}?page=2&page_size=2')
        self.assertEqual(len(response.data['results']), 2)
        self.assertIsNotNone(response.data['previous'])

    def test_list_invites_requires_auth(self):
        """Unauthenticated returns 401/403."""
        response = self.client.get(self.url)
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_list_invites_permission_denied(self):
        """User without can_invite gets 403."""
        user = UserWithAccountFactory(verified=True)
        user.account.can_invite = False
        user.account.save()

        self.client.force_login(user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AdminInviteRevokeTest(TestCase):
    """Tests for POST /api/v1/admin/invites/{id}/revoke/"""

    def setUp(self):
        self.client = APIClient()
        self.admin = UserWithAccountFactory(admin=True)

    def get_url(self, invite_id):
        return f'/api/v1/admin/invites/{invite_id}/revoke/'

    def test_revoke_pending_invite_success(self):
        """Revoke a pending EnrollmentKey."""
        ek = EnrollmentKeyFactory()

        self.client.force_login(self.admin)
        response = self.client.post(self.get_url(ek.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'revoked')
        self.assertIn('revoked_at', response.data)

        # Verify DB state
        ek.refresh_from_db()
        self.assertFalse(ek.is_active)
        self.assertIsNotNone(ek.revoked_at)

    def test_revoke_platform_invite_success(self):
        """Revoke a pending PlatformInvite."""
        pi = PlatformInviteFactory()

        self.client.force_login(self.admin)
        response = self.client.post(self.get_url(pi.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'revoked')

        # Verify DB state
        pi.refresh_from_db()
        self.assertFalse(pi.is_active)
        self.assertIsNotNone(pi.revoked_at)

    def test_revoke_already_accepted_error(self):
        """Error when trying to revoke accepted invite."""
        account = AccountFactory()
        ek = EnrollmentKeyFactory(used_by=account)

        self.client.force_login(self.admin)
        response = self.client.post(self.get_url(ek.id))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'ALREADY_ACCEPTED')

    def test_revoke_already_revoked_error(self):
        """Error when trying to revoke again."""
        ek = EnrollmentKeyFactory(is_active=False)

        self.client.force_login(self.admin)
        response = self.client.post(self.get_url(ek.id))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'ALREADY_REVOKED')

    def test_revoke_expired_invite_error(self):
        """Cannot revoke expired invite."""
        ek = EnrollmentKeyFactory(expired=True)

        self.client.force_login(self.admin)
        response = self.client.post(self.get_url(ek.id))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'EXPIRED')

    def test_revoke_not_found(self):
        """404 for non-existent invite."""
        import uuid
        fake_id = uuid.uuid4()

        self.client.force_login(self.admin)
        response = self.client.post(self.get_url(fake_id))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_revoke_org_admin_own_org(self):
        """Org admin can revoke their org's invite."""
        org = OrganizationFactory()
        user = UserWithAccountFactory(verified=True)
        user.account.organization = org
        user.account.can_invite = True
        user.account.save()

        ek = EnrollmentKeyFactory(organization=org)

        self.client.force_login(user)
        response = self.client.post(self.get_url(ek.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_revoke_org_admin_other_org_forbidden(self):
        """Org admin cannot revoke other org's invite."""
        org1 = OrganizationFactory()
        org2 = OrganizationFactory()

        user = UserWithAccountFactory(verified=True)
        user.account.organization = org1
        user.account.can_invite = True
        user.account.save()

        ek = EnrollmentKeyFactory(organization=org2)

        self.client.force_login(user)
        response = self.client.post(self.get_url(ek.id))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class AdminInviteResendTest(TestCase):
    """Tests for POST /api/v1/admin/invites/{id}/resend/"""

    def setUp(self):
        self.client = APIClient()
        self.admin = UserWithAccountFactory(admin=True)

    def get_url(self, invite_id):
        return f'/api/v1/admin/invites/{invite_id}/resend/'

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        EMAIL_HOST='smtp.test.com',
        STORMCLOUD_FRONTEND_URL='https://example.com',
    )
    def test_resend_enrollment_invite_success(self):
        """Resend email for pending EnrollmentKey."""
        from django.core import mail

        ek = EnrollmentKeyFactory(with_email=True)

        self.client.force_login(self.admin)
        response = self.client.post(self.get_url(ek.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], ek.required_email)
        self.assertIn('resent', response.data['message'].lower())

        # Verify email sent
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        EMAIL_HOST='smtp.test.com',
        STORMCLOUD_FRONTEND_URL='https://example.com',
    )
    def test_resend_platform_invite_success(self):
        """Resend email for pending PlatformInvite."""
        from django.core import mail

        pi = PlatformInviteFactory()

        self.client.force_login(self.admin)
        response = self.client.post(self.get_url(pi.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], pi.email)

        # Verify email sent
        self.assertEqual(len(mail.outbox), 1)

    def test_resend_accepted_invite_error(self):
        """Cannot resend for accepted invite."""
        account = AccountFactory()
        ek = EnrollmentKeyFactory(used_by=account, with_email=True)

        self.client.force_login(self.admin)
        response = self.client.post(self.get_url(ek.id))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'ALREADY_ACCEPTED')

    def test_resend_revoked_invite_error(self):
        """Cannot resend for revoked invite."""
        ek = EnrollmentKeyFactory(is_active=False, with_email=True)

        self.client.force_login(self.admin)
        response = self.client.post(self.get_url(ek.id))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'ALREADY_REVOKED')

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        EMAIL_HOST='smtp.test.com',
    )
    def test_resend_no_email_error(self):
        """Error if invite has no email."""
        ek = EnrollmentKeyFactory()  # No required_email

        self.client.force_login(self.admin)
        response = self.client.post(self.get_url(ek.id))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'NO_EMAIL')

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend',
        EMAIL_HOST='',
    )
    def test_resend_email_not_configured_error(self):
        """Error if EMAIL_BACKEND is console."""
        ek = EnrollmentKeyFactory(with_email=True)

        self.client.force_login(self.admin)
        response = self.client.post(self.get_url(ek.id))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'EMAIL_NOT_CONFIGURED')

    def test_resend_not_found(self):
        """404 for non-existent invite."""
        import uuid
        fake_id = uuid.uuid4()

        self.client.force_login(self.admin)
        response = self.client.post(self.get_url(fake_id))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
