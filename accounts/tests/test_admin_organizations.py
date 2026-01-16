"""Tests for admin organization management endpoints."""

from rest_framework import status

from core.tests.base import StormCloudAdminTestCase
from accounts.tests.factories import (
    UserWithAccountFactory,
    OrganizationFactory,
    AccountFactory,
)


class AdminOrganizationDetailTest(StormCloudAdminTestCase):
    """Tests for GET/PATCH /api/v1/admin/organizations/{org_id}/"""

    def test_get_org_detail(self):
        """Admin can get organization details."""
        org = OrganizationFactory(
            name="Test Org",
            slug="test-org",
            storage_quota_bytes=100 * 1024 * 1024,
        )
        # Add some members
        AccountFactory(organization=org)
        AccountFactory(organization=org)

        response = self.client.get(f"/api/v1/admin/organizations/{org.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data["id"], str(org.id))
        self.assertEqual(response.data["name"], "Test Org")
        self.assertEqual(response.data["slug"], "test-org")
        self.assertEqual(response.data["is_active"], True)
        self.assertEqual(response.data["storage_quota_bytes"], 100 * 1024 * 1024)
        self.assertEqual(response.data["member_count"], 2)
        self.assertIn("created_at", response.data)
        self.assertIn("updated_at", response.data)

    def test_get_org_not_found(self):
        """Returns 404 for non-existent organization."""
        import uuid

        fake_id = uuid.uuid4()

        response = self.client.get(f"/api/v1/admin/organizations/{fake_id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_org_name(self):
        """Admin can update organization name."""
        org = OrganizationFactory(name="Old Name")

        response = self.client.patch(
            f"/api/v1/admin/organizations/{org.id}/",
            {"name": "New Name"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "New Name")

        org.refresh_from_db()
        self.assertEqual(org.name, "New Name")

    def test_patch_org_slug(self):
        """Admin can update organization slug."""
        org = OrganizationFactory(slug="old-slug")

        response = self.client.patch(
            f"/api/v1/admin/organizations/{org.id}/",
            {"slug": "new-slug"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["slug"], "new-slug")

        org.refresh_from_db()
        self.assertEqual(org.slug, "new-slug")

    def test_patch_org_quota(self):
        """Admin can update organization storage quota."""
        org = OrganizationFactory(storage_quota_bytes=0)

        response = self.client.patch(
            f"/api/v1/admin/organizations/{org.id}/",
            {"storage_quota_bytes": 500 * 1024 * 1024},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["storage_quota_bytes"], 500 * 1024 * 1024)

        org.refresh_from_db()
        self.assertEqual(org.storage_quota_bytes, 500 * 1024 * 1024)

    def test_patch_org_is_active(self):
        """Admin can disable/enable organization."""
        org = OrganizationFactory(is_active=True)

        # Disable
        response = self.client.patch(
            f"/api/v1/admin/organizations/{org.id}/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["is_active"], False)

        org.refresh_from_db()
        self.assertFalse(org.is_active)

        # Re-enable
        response = self.client.patch(
            f"/api/v1/admin/organizations/{org.id}/",
            {"is_active": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        org.refresh_from_db()
        self.assertTrue(org.is_active)

    def test_patch_org_multiple_fields(self):
        """Admin can update multiple fields at once."""
        org = OrganizationFactory(
            name="Old Name",
            slug="old-slug",
            storage_quota_bytes=0,
        )

        response = self.client.patch(
            f"/api/v1/admin/organizations/{org.id}/",
            {
                "name": "New Name",
                "slug": "new-slug",
                "storage_quota_bytes": 100 * 1024 * 1024,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        org.refresh_from_db()
        self.assertEqual(org.name, "New Name")
        self.assertEqual(org.slug, "new-slug")
        self.assertEqual(org.storage_quota_bytes, 100 * 1024 * 1024)

    def test_patch_org_not_found(self):
        """Returns 404 for non-existent organization."""
        import uuid

        fake_id = uuid.uuid4()

        response = self.client.patch(
            f"/api/v1/admin/organizations/{fake_id}/",
            {"name": "Test"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_requires_admin(self):
        """Non-admin cannot update organization."""
        from accounts.tests.factories import APIKeyFactory

        org = OrganizationFactory()
        regular_user = UserWithAccountFactory(verified=True)
        regular_key = APIKeyFactory(user=regular_user)
        self.authenticate(api_key=regular_key)

        response = self.client.patch(
            f"/api/v1/admin/organizations/{org.id}/",
            {"name": "Hacked"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AdminOrganizationMembersTest(StormCloudAdminTestCase):
    """Tests for GET /api/v1/admin/organizations/{org_id}/members/"""

    def test_list_org_members(self):
        """Admin can list organization members."""
        org = OrganizationFactory(name="Test Org")
        account1 = AccountFactory(organization=org, is_owner=True)
        account2 = AccountFactory(organization=org, is_owner=False)

        response = self.client.get(f"/api/v1/admin/organizations/{org.id}/members/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data["organization_id"], str(org.id))
        self.assertEqual(response.data["organization_name"], "Test Org")
        self.assertEqual(response.data["total"], 2)
        self.assertEqual(len(response.data["members"]), 2)

        # Check member fields
        member = response.data["members"][0]
        self.assertIn("id", member)
        self.assertIn("username", member)
        self.assertIn("email", member)
        self.assertIn("is_owner", member)
        self.assertIn("storage_used_bytes", member)
        self.assertIn("storage_quota_bytes", member)
        self.assertIn("effective_quota_bytes", member)

    def test_members_includes_effective_quota(self):
        """Member list shows inherited quota when user has none."""
        org = OrganizationFactory(storage_quota_bytes=100 * 1024 * 1024)

        # User with personal quota
        account1 = AccountFactory(
            organization=org,
            storage_quota_bytes=50 * 1024 * 1024,
        )
        # User without personal quota (inherits from org)
        account2 = AccountFactory(
            organization=org,
            storage_quota_bytes=0,
        )

        response = self.client.get(f"/api/v1/admin/organizations/{org.id}/members/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Find the members
        member1 = next(
            m for m in response.data["members"] if m["id"] == account1.user.id
        )
        member2 = next(
            m for m in response.data["members"] if m["id"] == account2.user.id
        )

        # Member with personal quota
        self.assertEqual(member1["storage_quota_bytes"], 50 * 1024 * 1024)
        self.assertEqual(member1["effective_quota_bytes"], 50 * 1024 * 1024)

        # Member without personal quota - inherits from org
        self.assertIsNone(member2["storage_quota_bytes"])
        self.assertEqual(member2["effective_quota_bytes"], 100 * 1024 * 1024)

    def test_members_org_not_found(self):
        """Returns 404 for non-existent organization."""
        import uuid

        fake_id = uuid.uuid4()

        response = self.client.get(f"/api/v1/admin/organizations/{fake_id}/members/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_members_requires_admin(self):
        """Non-admin cannot list organization members."""
        from accounts.tests.factories import APIKeyFactory

        org = OrganizationFactory()
        regular_user = UserWithAccountFactory(verified=True)
        regular_key = APIKeyFactory(user=regular_user)
        self.authenticate(api_key=regular_key)

        response = self.client.get(f"/api/v1/admin/organizations/{org.id}/members/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_members_shows_storage_usage(self):
        """Member list includes storage usage for each member."""
        org = OrganizationFactory()
        account = AccountFactory(
            organization=org,
            storage_used_bytes=5 * 1024 * 1024,  # 5 MB
        )

        response = self.client.get(f"/api/v1/admin/organizations/{org.id}/members/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        member = response.data["members"][0]
        self.assertEqual(member["storage_used_bytes"], 5 * 1024 * 1024)
