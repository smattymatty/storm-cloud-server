"""Tests for CMS content flags API endpoints."""

from rest_framework import status

from cms.models import ContentFlag, ContentFlagHistory
from core.tests.base import StormCloudAPITestCase
from storage.models import StoredFile


class ContentFlagBaseTestCase(StormCloudAPITestCase):
    """Base test case with helper methods for flag tests."""

    def setUp(self):
        super().setUp()
        self.authenticate()
        # Create a test file
        self.test_file = StoredFile.objects.create(
            owner=self.user,
            path="test/document.md",
            name="document.md",
            size=1024,
            content_type="text/markdown",
            is_directory=False,
            parent_path="test",
        )

    def create_ai_flag(self, is_active=True, metadata=None):
        """Helper to create an ai_generated flag."""
        if metadata is None:
            metadata = {"model": "claude-3.5-sonnet"}
        return ContentFlag.objects.create(
            stored_file=self.test_file,
            flag_type="ai_generated",
            is_active=is_active,
            metadata=metadata,
            changed_by=self.user,
        )

    def create_approved_flag(self, is_active=True, metadata=None):
        """Helper to create a user_approved flag."""
        if metadata is None:
            metadata = {}
        return ContentFlag.objects.create(
            stored_file=self.test_file,
            flag_type="user_approved",
            is_active=is_active,
            metadata=metadata,
            changed_by=self.user,
        )


class SetFlagTests(ContentFlagBaseTestCase):
    """Tests for PUT /api/v1/cms/files/{path}/flags/{flag_type}/"""

    def test_set_ai_generated_flag(self):
        """Can set ai_generated flag with required metadata."""
        response = self.client.put(
            "/api/v1/cms/files/test/document.md/flags/ai_generated/",
            {
                "is_active": True,
                "metadata": {
                    "model": "claude-3.5-sonnet",
                    "prompt_context": "Generate about page copy",
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["flag_type"], "ai_generated")
        self.assertTrue(response.data["is_active"])
        self.assertEqual(response.data["metadata"]["model"], "claude-3.5-sonnet")

        # Verify database
        flag = ContentFlag.objects.get(stored_file=self.test_file, flag_type="ai_generated")
        self.assertTrue(flag.is_active)
        self.assertEqual(flag.metadata["model"], "claude-3.5-sonnet")

    def test_ai_generated_requires_model(self):
        """ai_generated flag requires model in metadata."""
        response = self.client.put(
            "/api/v1/cms/files/test/document.md/flags/ai_generated/",
            {
                "is_active": True,
                "metadata": {"prompt_context": "Generate copy"},  # Missing model
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("metadata", str(response.data))

    def test_user_approved_no_required_fields(self):
        """user_approved flag has no required metadata."""
        response = self.client.put(
            "/api/v1/cms/files/test/document.md/flags/user_approved/",
            {
                "is_active": True,
                "metadata": {},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["flag_type"], "user_approved")
        self.assertTrue(response.data["is_active"])

    def test_user_approved_with_notes(self):
        """user_approved flag accepts optional notes."""
        response = self.client.put(
            "/api/v1/cms/files/test/document.md/flags/user_approved/",
            {
                "is_active": True,
                "metadata": {"notes": "Reviewed by client on 2026-01-09"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["metadata"]["notes"], "Reviewed by client on 2026-01-09"
        )

    def test_flag_unknown_metadata_field_rejected(self):
        """Unknown metadata fields are rejected."""
        response = self.client.put(
            "/api/v1/cms/files/test/document.md/flags/ai_generated/",
            {
                "is_active": True,
                "metadata": {
                    "model": "claude-3.5-sonnet",
                    "unknown_field": "some value",  # Not allowed
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("metadata", str(response.data))

    def test_set_flag_on_nonexistent_file(self):
        """Setting flag on nonexistent file returns 404."""
        response = self.client.put(
            "/api/v1/cms/files/nonexistent/file.md/flags/ai_generated/",
            {
                "is_active": True,
                "metadata": {"model": "claude-3.5-sonnet"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "FILE_NOT_FOUND")

    def test_invalid_flag_type_rejected(self):
        """Invalid flag type returns 400."""
        response = self.client.put(
            "/api/v1/cms/files/test/document.md/flags/invalid_type/",
            {"is_active": True, "metadata": {}},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "INVALID_FLAG_TYPE")

    def test_update_existing_flag(self):
        """Updating existing flag works correctly."""
        # Create initial flag
        self.create_ai_flag(is_active=True)

        # Update it
        response = self.client.put(
            "/api/v1/cms/files/test/document.md/flags/ai_generated/",
            {
                "is_active": False,
                "metadata": {"model": "gpt-4", "notes": "Changed model"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_active"])
        self.assertEqual(response.data["metadata"]["model"], "gpt-4")


class FlagHistoryTests(ContentFlagBaseTestCase):
    """Tests for flag history functionality."""

    def test_flag_creates_history_on_update(self):
        """Changing a flag creates history entry."""
        # Create flag
        flag = self.create_ai_flag(is_active=True)
        self.assertEqual(ContentFlagHistory.objects.count(), 0)

        # Update flag via API
        response = self.client.put(
            "/api/v1/cms/files/test/document.md/flags/ai_generated/",
            {
                "is_active": False,
                "metadata": {"model": "gpt-4"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(ContentFlagHistory.objects.count(), 1)

        history = ContentFlagHistory.objects.first()
        self.assertTrue(history.was_active)
        self.assertFalse(history.is_active)

    def test_no_history_on_initial_creation(self):
        """Initial flag creation doesn't create history entry."""
        response = self.client.put(
            "/api/v1/cms/files/test/document.md/flags/ai_generated/",
            {
                "is_active": True,
                "metadata": {"model": "claude-3.5-sonnet"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(ContentFlagHistory.objects.count(), 0)

    def test_get_flag_history(self):
        """Can retrieve flag history via API."""
        # Create and update flag to generate history
        flag = self.create_ai_flag(is_active=True)
        flag.is_active = False
        flag.changed_by = self.user
        flag.save()

        response = self.client.get(
            "/api/v1/cms/files/test/document.md/flags/ai_generated/history/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["flag_type"], "ai_generated")
        self.assertEqual(len(response.data["history"]), 1)
        self.assertTrue(response.data["history"][0]["was_active"])
        self.assertFalse(response.data["history"][0]["is_active"])

    def test_history_for_nonexistent_flag_returns_404(self):
        """Getting history for unset flag returns 404."""
        response = self.client.get(
            "/api/v1/cms/files/test/document.md/flags/ai_generated/history/"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "FLAG_NOT_FOUND")


class GetFlagsTests(ContentFlagBaseTestCase):
    """Tests for GET /api/v1/cms/files/{path}/flags/"""

    def test_get_flags_for_file(self):
        """Can get all flags for a file."""
        self.create_ai_flag(is_active=True)

        response = self.client.get("/api/v1/cms/files/test/document.md/flags/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["file_path"], "test/document.md")
        self.assertEqual(len(response.data["flags"]), 2)  # ai_generated + user_approved

    def test_get_flags_includes_unset(self):
        """GET flags returns all flag types even if unset."""
        response = self.client.get("/api/v1/cms/files/test/document.md/flags/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        flags_by_type = {f["flag_type"]: f for f in response.data["flags"]}

        self.assertIn("ai_generated", flags_by_type)
        self.assertIn("user_approved", flags_by_type)
        self.assertFalse(flags_by_type["ai_generated"]["is_active"])
        self.assertFalse(flags_by_type["user_approved"]["is_active"])

    def test_get_flags_nonexistent_file_returns_404(self):
        """Getting flags for nonexistent file returns 404."""
        response = self.client.get("/api/v1/cms/files/nonexistent/file.md/flags/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class PendingReviewTests(ContentFlagBaseTestCase):
    """Tests for GET /api/v1/cms/flags/pending/"""

    def test_pending_review_query(self):
        """Pending returns ai_generated=true AND user_approved!=true."""
        # Create file with ai_generated=true, user_approved=false
        self.create_ai_flag(is_active=True)

        response = self.client.get("/api/v1/cms/flags/pending/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["files"][0]["file_path"], "test/document.md")
        self.assertTrue(response.data["files"][0]["needs_review"])

    def test_approved_file_not_in_pending(self):
        """File with user_approved=true not in pending list."""
        self.create_ai_flag(is_active=True)
        self.create_approved_flag(is_active=True)

        response = self.client.get("/api/v1/cms/flags/pending/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

    def test_non_ai_file_not_in_pending(self):
        """File without ai_generated flag not in pending list."""
        # Only create user_approved flag
        self.create_approved_flag(is_active=True)

        response = self.client.get("/api/v1/cms/flags/pending/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)


class FlagListTests(ContentFlagBaseTestCase):
    """Tests for GET /api/v1/cms/flags/"""

    def test_list_files_with_flags(self):
        """Can list files with any flags."""
        self.create_ai_flag(is_active=True)

        response = self.client.get("/api/v1/cms/flags/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_filter_by_ai_generated(self):
        """Can filter by ai_generated status."""
        self.create_ai_flag(is_active=True)

        # Filter for ai_generated=true
        response = self.client.get("/api/v1/cms/flags/?ai_generated=true")
        self.assertEqual(response.data["count"], 1)

        # Filter for ai_generated=false
        response = self.client.get("/api/v1/cms/flags/?ai_generated=false")
        self.assertEqual(response.data["count"], 0)

    def test_filter_by_needs_review(self):
        """Can filter by needs_review status."""
        self.create_ai_flag(is_active=True)

        response = self.client.get("/api/v1/cms/flags/?needs_review=true")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)


class FlagCascadeDeleteTests(ContentFlagBaseTestCase):
    """Tests for cascade deletion when file is deleted."""

    def test_flag_cascade_delete(self):
        """Flag deleted when file deleted (filesystem wins)."""
        self.create_ai_flag(is_active=True)
        self.assertEqual(ContentFlag.objects.count(), 1)

        # Delete the file
        self.test_file.delete()

        # Flag should be cascade deleted
        self.assertEqual(ContentFlag.objects.count(), 0)

    def test_flag_history_cascade_delete(self):
        """Flag history deleted when flag deleted."""
        flag = self.create_ai_flag(is_active=True)
        flag.is_active = False
        flag.save()  # Creates history
        self.assertEqual(ContentFlagHistory.objects.count(), 1)

        # Delete the file (cascades to flag, then to history)
        self.test_file.delete()

        self.assertEqual(ContentFlag.objects.count(), 0)
        self.assertEqual(ContentFlagHistory.objects.count(), 0)


class FlagAuthTests(ContentFlagBaseTestCase):
    """Tests for authentication requirements."""

    def test_set_flag_requires_auth(self):
        """Setting flag requires authentication."""
        self.client.credentials()  # Remove auth
        response = self.client.put(
            "/api/v1/cms/files/test/document.md/flags/ai_generated/",
            {"is_active": True, "metadata": {"model": "test"}},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_flags_requires_auth(self):
        """Getting flags requires authentication."""
        self.client.credentials()  # Remove auth
        response = self.client.get("/api/v1/cms/files/test/document.md/flags/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_access_other_users_file_flags(self):
        """Cannot access flags on another user's file."""
        # Create another user and their file
        from django.contrib.auth import get_user_model
        User = get_user_model()
        other_user = User.objects.create_user(username="other", password="pass")
        other_file = StoredFile.objects.create(
            owner=other_user,
            path="other/secret.md",
            name="secret.md",
            size=512,
            content_type="text/markdown",
            is_directory=False,
            parent_path="other",
        )

        # Try to access other user's file flags
        response = self.client.get("/api/v1/cms/files/other/secret.md/flags/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
