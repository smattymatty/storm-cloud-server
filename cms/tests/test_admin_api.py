"""Tests for admin CMS API endpoints."""

from datetime import timedelta
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status

from accounts.tests.factories import APIKeyFactory, UserWithProfileFactory
from cms.models import ContentFlag, ContentFlagHistory, PageFileMapping, PageStats
from core.tests.base import StormCloudAdminTestCase
from storage.models import StoredFile

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser as User
else:
    User = get_user_model()


class AdminCmsTestMixin:
    """Mixin with helper methods for admin CMS tests."""

    def _create_stored_file(self, user: User, path: str) -> StoredFile:
        """Create a StoredFile record for a user."""
        parent_path = "/".join(path.split("/")[:-1]) if "/" in path else ""
        return StoredFile.objects.create(
            owner=user.account,
            path=path,
            name=path.split("/")[-1],
            size=1024,
            content_type="text/markdown",
            is_directory=False,
            parent_path=parent_path,
            encryption_method="none",
        )

    def _create_page_mapping(
        self, user: User, page_path: str, file_path: str, stale: bool = False
    ) -> PageFileMapping:
        """Create a PageFileMapping for a user."""
        mapping = PageFileMapping.objects.create(
            owner=user,
            page_path=page_path,
            file_path=file_path,
        )
        if stale:
            # Make it stale (older than 24 hours)
            stale_time = timezone.now() - timedelta(hours=48)
            PageFileMapping.objects.filter(pk=mapping.pk).update(last_seen=stale_time)
            mapping.refresh_from_db()
        return mapping

    def _create_page_stats(
        self, user: User, page_path: str, view_count: int = 1
    ) -> PageStats:
        """Create PageStats for a user."""
        return PageStats.objects.create(
            owner=user,
            page_path=page_path,
            view_count=view_count,
        )

    def _create_flag(
        self,
        stored_file: StoredFile,
        flag_type: str,
        is_active: bool = True,
        changed_by: "User | None" = None,
        metadata: dict | None = None,
    ) -> ContentFlag:
        """Create a ContentFlag for a file."""
        if metadata is None:
            metadata = (
                {"model": "claude-3.5-sonnet"} if flag_type == "ai_generated" else {}
            )
        return ContentFlag.objects.create(
            stored_file=stored_file,
            flag_type=flag_type,
            is_active=is_active,
            metadata=metadata,
            changed_by=changed_by,
        )


# =============================================================================
# Page List Tests
# =============================================================================


class AdminPageListTests(AdminCmsTestMixin, StormCloudAdminTestCase):
    """Tests for GET /api/v1/admin/users/{id}/cms/pages/"""

    def setUp(self):
        super().setUp()
        self.target_user = UserWithProfileFactory(verified=True)

    def test_admin_list_user_pages(self):
        """Admin can list another user's CMS pages."""
        self._create_page_mapping(self.target_user, "/about", "content/about.md")
        self._create_page_mapping(self.target_user, "/about", "content/team.md")
        self._create_page_mapping(self.target_user, "/contact", "content/contact.md")
        self._create_page_stats(self.target_user, "/about", view_count=10)

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/cms/pages/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 2)  # 2 unique pages
        self.assertIn("target_user", response.data)
        self.assertEqual(response.data["target_user"]["id"], self.target_user.id)

        # Find /about page and verify file count
        about_page = next(
            p for p in response.data["pages"] if p["page_path"] == "/about"
        )
        self.assertEqual(about_page["file_count"], 2)
        self.assertEqual(about_page["view_count"], 10)

    def test_admin_list_stale_pages(self):
        """Admin can filter stale pages."""
        self._create_page_mapping(self.target_user, "/fresh", "content/fresh.md")
        self._create_page_mapping(
            self.target_user, "/stale", "content/stale.md", stale=True
        )

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/cms/pages/?stale=true"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 1)
        self.assertEqual(response.data["pages"][0]["page_path"], "/stale")
        self.assertTrue(response.data["pages"][0]["is_stale"])

    def test_list_nonexistent_user_returns_404(self):
        """Returns 404 for invalid user_id."""
        response = self.client.get("/api/v1/admin/users/99999/cms/pages/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_admin_gets_403(self):
        """Regular user cannot access admin endpoint."""
        regular_user = UserWithProfileFactory(verified=True)
        regular_key = APIKeyFactory(user=regular_user)
        self.authenticate(api_key=regular_key)

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/cms/pages/"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# =============================================================================
# Page Detail Tests
# =============================================================================


class AdminPageDetailTests(AdminCmsTestMixin, StormCloudAdminTestCase):
    """Tests for GET/DELETE /api/v1/admin/users/{id}/cms/pages/{path}/"""

    def setUp(self):
        super().setUp()
        self.target_user = UserWithProfileFactory(verified=True)

    def test_admin_get_page_detail(self):
        """Admin can get files on a user's page."""
        file1 = self._create_stored_file(self.target_user, "content/about.md")
        file2 = self._create_stored_file(self.target_user, "content/team.md")
        self._create_page_mapping(self.target_user, "/about", "content/about.md")
        self._create_page_mapping(self.target_user, "/about", "content/team.md")
        self._create_page_stats(self.target_user, "/about", view_count=5)

        # Add a flag to one file
        self._create_flag(file1, "ai_generated", is_active=True)

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/cms/pages/about/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["page_path"], "/about")
        self.assertEqual(len(response.data["files"]), 2)
        self.assertEqual(response.data["view_count"], 5)
        self.assertIn("target_user", response.data)

        # Check flag on first file
        about_file = next(
            f for f in response.data["files"] if f["file_path"] == "content/about.md"
        )
        self.assertTrue(about_file["flags"]["ai_generated"])

    def test_admin_delete_page_mappings(self):
        """Admin can delete all mappings for a user's page."""
        self._create_page_mapping(self.target_user, "/old-page", "content/old1.md")
        self._create_page_mapping(self.target_user, "/old-page", "content/old2.md")

        response = self.client.delete(
            f"/api/v1/admin/users/{self.target_user.id}/cms/pages/old-page/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["deleted"], 2)
        self.assertIn("target_user", response.data)

        # Verify mappings are gone
        self.assertEqual(
            PageFileMapping.objects.filter(
                owner=self.target_user, page_path="/old-page"
            ).count(),
            0,
        )

    def test_get_nonexistent_page_returns_404(self):
        """Returns 404 for page with no mappings."""
        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/cms/pages/nonexistent/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# =============================================================================
# Page Flags Tests
# =============================================================================


class AdminPageFlagsTests(AdminCmsTestMixin, StormCloudAdminTestCase):
    """Tests for GET /api/v1/admin/users/{id}/cms/pages/flags/"""

    def setUp(self):
        super().setUp()
        self.target_user = UserWithProfileFactory(verified=True)

    def test_admin_get_page_flags(self):
        """Admin can get aggregated flag counts per page."""
        file1 = self._create_stored_file(self.target_user, "content/about.md")
        file2 = self._create_stored_file(self.target_user, "content/team.md")
        self._create_page_mapping(self.target_user, "/about", "content/about.md")
        self._create_page_mapping(self.target_user, "/about", "content/team.md")

        # Add flags
        self._create_flag(file1, "ai_generated", is_active=True)
        self._create_flag(file2, "ai_generated", is_active=True)
        self._create_flag(file1, "user_approved", is_active=True)

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/cms/pages/flags/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("target_user", response.data)

        about_page = next(
            p for p in response.data["pages"] if p["page_path"] == "/about"
        )
        self.assertEqual(about_page["flags"]["ai_generated"], 2)
        self.assertEqual(about_page["flags"]["user_approved"], 1)


# =============================================================================
# Flag List Tests
# =============================================================================


class AdminFlagListTests(AdminCmsTestMixin, StormCloudAdminTestCase):
    """Tests for GET /api/v1/admin/users/{id}/cms/flags/"""

    def setUp(self):
        super().setUp()
        self.target_user = UserWithProfileFactory(verified=True)

    def test_admin_list_flagged_files(self):
        """Admin can list user's files with flags."""
        file1 = self._create_stored_file(self.target_user, "content/ai-content.md")
        file2 = self._create_stored_file(self.target_user, "content/approved.md")

        self._create_flag(file1, "ai_generated", is_active=True)
        self._create_flag(file2, "ai_generated", is_active=True)
        self._create_flag(file2, "user_approved", is_active=True)

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/cms/flags/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertIn("target_user", response.data)

    def test_admin_filter_needs_review(self):
        """Admin can filter files needing review."""
        file1 = self._create_stored_file(self.target_user, "content/needs-review.md")
        file2 = self._create_stored_file(self.target_user, "content/approved.md")

        self._create_flag(file1, "ai_generated", is_active=True)
        self._create_flag(file2, "ai_generated", is_active=True)
        self._create_flag(file2, "user_approved", is_active=True)

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/cms/flags/?needs_review=true"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["files"][0]["file_path"], "content/needs-review.md"
        )


# =============================================================================
# Pending Review Tests
# =============================================================================


class AdminPendingReviewTests(AdminCmsTestMixin, StormCloudAdminTestCase):
    """Tests for GET /api/v1/admin/users/{id}/cms/flags/pending/"""

    def setUp(self):
        super().setUp()
        self.target_user = UserWithProfileFactory(verified=True)

    def test_admin_list_pending_review(self):
        """Admin can list user's files pending review."""
        file1 = self._create_stored_file(self.target_user, "content/pending.md")
        file2 = self._create_stored_file(self.target_user, "content/approved.md")

        self._create_flag(file1, "ai_generated", is_active=True)
        self._create_flag(file2, "ai_generated", is_active=True)
        self._create_flag(file2, "user_approved", is_active=True)

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/cms/flags/pending/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertTrue(response.data["files"][0]["needs_review"])
        self.assertIn("target_user", response.data)


# =============================================================================
# File Flags Tests
# =============================================================================


class AdminFileFlagsTests(AdminCmsTestMixin, StormCloudAdminTestCase):
    """Tests for GET /api/v1/admin/users/{id}/cms/files/{path}/flags/"""

    def setUp(self):
        super().setUp()
        self.target_user = UserWithProfileFactory(verified=True)
        self.test_file = self._create_stored_file(self.target_user, "content/test.md")

    def test_admin_get_file_flags(self):
        """Admin can get all flags for a user's file."""
        self._create_flag(self.test_file, "ai_generated", is_active=True)

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/cms/files/content/test.md/flags/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["file_path"], "content/test.md")
        self.assertEqual(len(response.data["flags"]), 2)  # Both flag types returned
        self.assertIn("target_user", response.data)

        # Find ai_generated flag
        ai_flag = next(
            f for f in response.data["flags"] if f["flag_type"] == "ai_generated"
        )
        self.assertTrue(ai_flag["is_active"])

    def test_get_flags_nonexistent_file_returns_404(self):
        """Returns 404 for nonexistent file."""
        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/cms/files/nonexistent.md/flags/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# =============================================================================
# Set Flag Tests
# =============================================================================


class AdminSetFlagTests(AdminCmsTestMixin, StormCloudAdminTestCase):
    """Tests for PUT /api/v1/admin/users/{id}/cms/files/{path}/flags/{flag_type}/"""

    def setUp(self):
        super().setUp()
        self.target_user = UserWithProfileFactory(verified=True)
        self.test_file = self._create_stored_file(self.target_user, "content/test.md")

    def test_admin_set_flag(self):
        """Admin can set a flag on a user's file."""
        response = self.client.put(
            f"/api/v1/admin/users/{self.target_user.id}/cms/files/content/test.md/flags/ai_generated/",
            {
                "is_active": True,
                "metadata": {"model": "claude-3.5-sonnet"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_active"])
        self.assertIn("target_user", response.data)

        # Verify flag was created
        flag = ContentFlag.objects.get(
            stored_file=self.test_file, flag_type="ai_generated"
        )
        self.assertTrue(flag.is_active)

    def test_admin_set_flag_records_admin_as_changed_by(self):
        """When admin sets flag, changed_by is the admin (audit trail)."""
        response = self.client.put(
            f"/api/v1/admin/users/{self.target_user.id}/cms/files/content/test.md/flags/user_approved/",
            {
                "is_active": True,
                "metadata": {"notes": "Approved by admin"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify changed_by is the admin, NOT the target user
        flag = ContentFlag.objects.get(
            stored_file=self.test_file, flag_type="user_approved"
        )
        self.assertEqual(flag.changed_by, self.admin)
        self.assertNotEqual(flag.changed_by, self.target_user)

    def test_admin_update_flag_creates_history(self):
        """Updating a flag creates history entry with admin as changed_by."""
        # Create initial flag
        flag = self._create_flag(
            self.test_file, "ai_generated", is_active=True, changed_by=self.target_user
        )

        # Admin updates the flag
        response = self.client.put(
            f"/api/v1/admin/users/{self.target_user.id}/cms/files/content/test.md/flags/ai_generated/",
            {
                "is_active": False,
                "metadata": {"model": "claude-3.5-sonnet"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify history was created
        history = ContentFlagHistory.objects.filter(flag=flag).first()
        self.assertIsNotNone(history)
        self.assertTrue(history.was_active)
        self.assertFalse(history.is_active)
        self.assertEqual(history.changed_by, self.admin)

    def test_set_flag_invalid_type_returns_400(self):
        """Invalid flag type returns 400."""
        response = self.client.put(
            f"/api/v1/admin/users/{self.target_user.id}/cms/files/content/test.md/flags/invalid_type/",
            {"is_active": True, "metadata": {}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# =============================================================================
# Flag History Tests
# =============================================================================


class AdminFlagHistoryTests(AdminCmsTestMixin, StormCloudAdminTestCase):
    """Tests for GET /api/v1/admin/users/{id}/cms/files/{path}/flags/{flag_type}/history/"""

    def setUp(self):
        super().setUp()
        self.target_user = UserWithProfileFactory(verified=True)
        self.test_file = self._create_stored_file(self.target_user, "content/test.md")

    def test_admin_get_flag_history(self):
        """Admin can get flag history for a user's file."""
        flag = self._create_flag(
            self.test_file, "ai_generated", is_active=True, changed_by=self.target_user
        )

        # Update the flag to create history
        flag.is_active = False
        flag.changed_by = self.admin
        flag.save()

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/cms/files/content/test.md/flags/ai_generated/history/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["flag_type"], "ai_generated")
        self.assertEqual(len(response.data["history"]), 1)
        self.assertIn("target_user", response.data)

    def test_get_history_nonexistent_flag_returns_404(self):
        """Returns 404 for flag that doesn't exist."""
        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/cms/files/content/test.md/flags/ai_generated/history/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# =============================================================================
# Stale Cleanup Tests
# =============================================================================


class AdminStaleCleanupTests(AdminCmsTestMixin, StormCloudAdminTestCase):
    """Tests for POST /api/v1/admin/users/{id}/cms/cleanup/"""

    def setUp(self):
        super().setUp()
        self.target_user = UserWithProfileFactory(verified=True)

    def test_admin_cleanup_stale_mappings(self):
        """Admin can cleanup stale mappings for a user."""
        self._create_page_mapping(self.target_user, "/fresh", "content/fresh.md")
        self._create_page_mapping(
            self.target_user, "/stale", "content/stale.md", stale=True
        )

        response = self.client.post(
            f"/api/v1/admin/users/{self.target_user.id}/cms/cleanup/",
            {"hours": 24},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["deleted"], 1)
        self.assertEqual(response.data["threshold_hours"], 24)
        self.assertIn("target_user", response.data)

        # Verify stale mapping is gone, fresh remains
        self.assertEqual(
            PageFileMapping.objects.filter(owner=self.target_user).count(), 1
        )

    def test_cleanup_minimum_hours_validation(self):
        """Cleanup requires minimum 24 hours threshold."""
        response = self.client.post(
            f"/api/v1/admin/users/{self.target_user.id}/cms/cleanup/",
            {"hours": 12},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("24 hours", response.data["error"])
