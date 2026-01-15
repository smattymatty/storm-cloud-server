"""Tests for two-step platform enrollment flow."""

from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Account, Organization, PlatformInvite
from accounts.tests.factories import UserWithProfileFactory


User = get_user_model()


class PlatformInviteCreateTestCase(TestCase):
    """Tests for creating platform invites (admin only)."""

    def setUp(self):
        self.client = APIClient()
        self.admin = UserWithProfileFactory(admin=True)
        self.url = reverse('platform-invite-create')

    def test_create_invite_as_admin(self):
        """Admin can create a platform invite."""
        self.client.force_login(self.admin)

        response = self.client.post(self.url, {
            'email': 'client@example.com',
            'name': 'Acme Corp Onboarding',
            'quota_gb': 100,
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('key', response.data)
        self.assertTrue(response.data['key'].startswith('pi_'))
        self.assertEqual(response.data['email'], 'client@example.com')
        self.assertEqual(response.data['quota_gb'], 100)

    def test_create_invite_requires_admin(self):
        """Non-admin cannot create platform invite."""
        user = UserWithProfileFactory()
        self.client.force_login(user)

        response = self.client.post(self.url, {
            'email': 'client@example.com',
            'name': 'Test',
        })

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_invite_unauthenticated(self):
        """Unauthenticated request cannot create invite."""
        response = self.client.post(self.url, {
            'email': 'client@example.com',
            'name': 'Test',
        })

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class PlatformInviteValidateTestCase(TestCase):
    """Tests for validating platform invite tokens."""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse('platform-invite-validate')
        self.invite = PlatformInvite.objects.create(
            email='client@example.com',
            name='Test Invite',
            expires_at=timezone.now() + timedelta(days=7),
        )

    def test_validate_valid_token(self):
        """Valid token returns invite details."""
        response = self.client.post(self.url, {'token': self.invite.key})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'client@example.com')
        self.assertTrue(response.data['is_valid'])

    def test_validate_invalid_token(self):
        """Invalid token returns 404."""
        response = self.client.post(self.url, {'token': 'pi_invalid_token'})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['error']['code'], 'INVALID_TOKEN')

    def test_validate_expired_token(self):
        """Expired token shows invalid."""
        self.invite.expires_at = timezone.now() - timedelta(days=1)
        self.invite.save()

        response = self.client.post(self.url, {'token': self.invite.key})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['is_valid'])
        self.assertEqual(response.data['invalid_reason'], 'expired')

    def test_validate_used_token(self):
        """Used token shows invalid."""
        self.invite.is_used = True
        self.invite.save()

        response = self.client.post(self.url, {'token': self.invite.key})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['is_valid'])
        self.assertEqual(response.data['invalid_reason'], 'already_used')


class PlatformEnrollStep1TestCase(TestCase):
    """Tests for step 1: Create user account."""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse('platform-enroll')
        self.invite = PlatformInvite.objects.create(
            email='client@example.com',
            name='Test Invite',
            quota_bytes=100 * 1024 * 1024 * 1024,  # 100 GB
            expires_at=timezone.now() + timedelta(days=7),
        )

    def test_enroll_creates_user(self):
        """Valid enrollment creates user and sets session."""
        response = self.client.post(self.url, {
            'token': self.invite.key,
            'username': 'newclient',
            'email': 'client@example.com',
            'password': 'SecurePass123!',
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['username'], 'newclient')
        self.assertTrue(response.data['needs_org_setup'])
        self.assertEqual(response.data['invite_name'], 'Test Invite')
        self.assertEqual(response.data['quota_gb'], 100)

        # User created
        user = User.objects.get(username='newclient')
        self.assertEqual(user.email, 'client@example.com')

        # User linked to invite
        self.invite.refresh_from_db()
        self.assertEqual(self.invite.enrolled_user, user)
        self.assertFalse(self.invite.is_used)  # Not fully used yet

        # Session set (user logged in)
        self.assertTrue('_auth_user_id' in self.client.session)

    def test_enroll_invalid_token(self):
        """Invalid token returns error."""
        response = self.client.post(self.url, {
            'token': 'pi_invalid',
            'username': 'newclient',
            'email': 'client@example.com',
            'password': 'SecurePass123!',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'INVALID_TOKEN')

    def test_enroll_email_mismatch(self):
        """Email must match invite."""
        response = self.client.post(self.url, {
            'token': self.invite.key,
            'username': 'newclient',
            'email': 'wrong@example.com',
            'password': 'SecurePass123!',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'EMAIL_MISMATCH')

    def test_enroll_expired_invite(self):
        """Expired invite returns error."""
        self.invite.expires_at = timezone.now() - timedelta(days=1)
        self.invite.save()

        response = self.client.post(self.url, {
            'token': self.invite.key,
            'username': 'newclient',
            'email': 'client@example.com',
            'password': 'SecurePass123!',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'INVALID_INVITE')

    def test_enroll_already_used_invite(self):
        """Already used invite returns error."""
        self.invite.is_used = True
        self.invite.save()

        response = self.client.post(self.url, {
            'token': self.invite.key,
            'username': 'newclient',
            'email': 'client@example.com',
            'password': 'SecurePass123!',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'INVALID_INVITE')

    def test_enroll_already_enrolled(self):
        """Invite with enrolled_user returns specific error."""
        existing_user = User.objects.create_user(
            username='existing',
            email='other@example.com',
            password='pass',
        )
        self.invite.enrolled_user = existing_user
        self.invite.save()

        response = self.client.post(self.url, {
            'token': self.invite.key,
            'username': 'newclient',
            'email': 'client@example.com',
            'password': 'SecurePass123!',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'ALREADY_ENROLLED')

    def test_enroll_duplicate_username(self):
        """Duplicate username returns validation error."""
        User.objects.create_user(username='taken', email='x@x.com', password='pass')

        response = self.client.post(self.url, {
            'token': self.invite.key,
            'username': 'taken',
            'email': 'client@example.com',
            'password': 'SecurePass123!',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data)

    def test_enroll_duplicate_email(self):
        """Duplicate email returns validation error."""
        User.objects.create_user(
            username='other',
            email='client@example.com',
            password='pass',
        )

        response = self.client.post(self.url, {
            'token': self.invite.key,
            'username': 'newclient',
            'email': 'client@example.com',
            'password': 'SecurePass123!',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

    def test_enroll_weak_password(self):
        """Weak password returns validation error."""
        response = self.client.post(self.url, {
            'token': self.invite.key,
            'username': 'newclient',
            'email': 'client@example.com',
            'password': '123',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)


class PlatformSetupOrgStep2TestCase(TestCase):
    """Tests for step 2: Create organization."""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse('platform-setup-org')

        # Create user who completed step 1
        self.user = User.objects.create_user(
            username='newclient',
            email='client@example.com',
            password='SecurePass123!',
        )
        self.invite = PlatformInvite.objects.create(
            email='client@example.com',
            name='Test Invite',
            quota_bytes=100 * 1024 * 1024 * 1024,
            expires_at=timezone.now() + timedelta(days=7),
            enrolled_user=self.user,
        )

    def test_setup_org_success(self):
        """Valid setup creates org and account."""
        self.client.force_login(self.user)

        response = self.client.post(self.url, {
            'organization_name': 'Acme Corp',
            'organization_slug': 'acme',
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['organization_name'], 'Acme Corp')
        self.assertEqual(response.data['organization_slug'], 'acme')
        self.assertIn('organization_id', response.data)
        self.assertIn('account_id', response.data)

        # Org created with quota from invite
        org = Organization.objects.get(slug='acme')
        self.assertEqual(org.storage_quota_bytes, 100 * 1024 * 1024 * 1024)

        # Account created as owner
        account = Account.objects.get(user=self.user)
        self.assertEqual(account.organization, org)
        self.assertTrue(account.is_owner)
        self.assertTrue(account.can_invite)
        self.assertTrue(account.can_manage_members)
        self.assertTrue(account.can_manage_api_keys)

        # Invite marked as used
        self.invite.refresh_from_db()
        self.assertTrue(self.invite.is_used)
        self.assertEqual(self.invite.used_by, account)
        self.assertIsNone(self.invite.enrolled_user)

    def test_setup_org_auto_slug(self):
        """Org slug auto-generated if not provided."""
        self.client.force_login(self.user)

        response = self.client.post(self.url, {
            'organization_name': 'Acme Corp',
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(len(response.data['organization_slug']) > 0)

    def test_setup_org_requires_auth(self):
        """Unauthenticated request rejected."""
        response = self.client.post(self.url, {
            'organization_name': 'Acme Corp',
        })

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_setup_org_no_pending_invite(self):
        """User without pending invite gets error."""
        user_no_invite = User.objects.create_user(
            username='random',
            email='random@example.com',
            password='pass',
        )
        self.client.force_login(user_no_invite)

        response = self.client.post(self.url, {
            'organization_name': 'Acme Corp',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'NO_PENDING_INVITE')

    def test_setup_org_already_has_account(self):
        """User who already has account gets error."""
        # Give user an account already
        org = Organization.objects.create(name='Existing Org')
        Account.objects.create(user=self.user, organization=org)

        self.client.force_login(self.user)

        response = self.client.post(self.url, {
            'organization_name': 'Acme Corp',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'ALREADY_HAS_ACCOUNT')

    def test_setup_org_duplicate_slug(self):
        """Duplicate slug returns validation error."""
        Organization.objects.create(name='Other', slug='taken')
        self.client.force_login(self.user)

        response = self.client.post(self.url, {
            'organization_name': 'Acme Corp',
            'organization_slug': 'taken',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('organization_slug', response.data)


class PlatformEnrollmentFullFlowTestCase(TestCase):
    """Integration tests for complete enrollment flow."""

    def setUp(self):
        self.client = APIClient()
        self.admin = UserWithProfileFactory(admin=True)

    def test_full_enrollment_flow(self):
        """Test complete enrollment from invite creation to org setup."""
        # Step 0: Admin creates invite
        self.client.force_login(self.admin)
        response = self.client.post(reverse('platform-invite-create'), {
            'email': 'ceo@newcorp.com',
            'name': 'NewCorp Onboarding',
            'quota_gb': 50,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        token = response.data['key']

        # Clear session (simulate new browser)
        self.client.logout()

        # Step 1: Client validates invite
        response = self.client.post(reverse('platform-invite-validate'), {
            'token': token,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['is_valid'])

        # Step 2: Client enrolls (creates user)
        response = self.client.post(reverse('platform-enroll'), {
            'token': token,
            'username': 'ceo',
            'email': 'ceo@newcorp.com',
            'password': 'VerySecure123!',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['needs_org_setup'])

        # User is now logged in (session set)
        self.assertTrue('_auth_user_id' in self.client.session)

        # Step 3: Client sets up organization
        response = self.client.post(reverse('platform-setup-org'), {
            'organization_name': 'NewCorp Inc',
            'organization_slug': 'newcorp',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['organization_name'], 'NewCorp Inc')

        # Verify final state
        user = User.objects.get(username='ceo')
        account = Account.objects.get(user=user)
        org = Organization.objects.get(slug='newcorp')

        self.assertEqual(account.organization, org)
        self.assertTrue(account.is_owner)
        self.assertEqual(org.storage_quota_bytes, 50 * 1024 * 1024 * 1024)

        invite = PlatformInvite.objects.get(key=token)
        self.assertTrue(invite.is_used)
        self.assertEqual(invite.used_by, account)
