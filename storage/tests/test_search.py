"""Tests for recursive file search API endpoints."""

import uuid
from pathlib import Path

from django.contrib.auth import get_user_model
from rest_framework import status

from core.tests.base import StormCloudAPITestCase, StormCloudAdminTestCase

User = get_user_model()


class SearchFilesViewTest(StormCloudAPITestCase):
    """Tests for GET /api/v1/search/files/"""

    def setUp(self):
        super().setUp()
        self.authenticate()
        # Create test directory structure
        user_storage = self.test_storage_root / str(self.user.account.id)
        user_storage.mkdir(parents=True, exist_ok=True)

        # Create some files and directories for search
        (user_storage / "readme.md").write_text("# Readme")
        (user_storage / "readme.txt").write_text("Readme text")
        (user_storage / "docs").mkdir(exist_ok=True)
        (user_storage / "docs" / "guide.md").write_text("Guide")
        (user_storage / "docs" / "api-readme.md").write_text("API docs")
        (user_storage / "archive").mkdir(exist_ok=True)
        (user_storage / "archive" / "old-readme.md").write_text("Old")
        (user_storage / "config.json").write_text("{}")

    def test_search_requires_query_param(self):
        """Search without q param returns 400."""
        response = self.client.get("/api/v1/search/files/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "MISSING_QUERY")

    def test_search_empty_query_returns_400(self):
        """Search with empty q param returns 400."""
        response = self.client.get("/api/v1/search/files/?q=")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "MISSING_QUERY")

    def test_search_finds_files_by_name(self):
        """Search finds files containing query in filename."""
        response = self.client.get("/api/v1/search/files/?q=readme")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 4)  # All readme files
        names = [r["name"] for r in response.data["results"]]
        self.assertIn("readme.md", names)
        self.assertIn("readme.txt", names)
        self.assertIn("api-readme.md", names)
        self.assertIn("old-readme.md", names)

    def test_search_finds_directories(self):
        """Search finds directories containing query in name."""
        response = self.client.get("/api/v1/search/files/?q=docs")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["count"], 1)
        dir_result = next(
            (r for r in response.data["results"] if r["name"] == "docs"), None
        )
        self.assertIsNotNone(dir_result)
        self.assertEqual(dir_result["type"], "directory")

    def test_search_is_case_insensitive(self):
        """Search is case-insensitive."""
        response = self.client.get("/api/v1/search/files/?q=README")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 4)

    def test_search_from_path(self):
        """Search with path param starts from that directory."""
        response = self.client.get("/api/v1/search/files/?q=readme&path=docs")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "api-readme.md")
        self.assertEqual(response.data["search_path"], "/docs")

    def test_search_with_limit(self):
        """Search respects limit param."""
        response = self.client.get("/api/v1/search/files/?q=readme&limit=2")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertTrue(response.data["truncated"])

    def test_search_path_not_found(self):
        """Search with nonexistent path returns 404."""
        response = self.client.get("/api/v1/search/files/?q=test&path=nonexistent")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "PATH_NOT_FOUND")

    def test_search_path_traversal_blocked(self):
        """Search blocks path traversal."""
        response = self.client.get("/api/v1/search/files/?q=test&path=../other")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "INVALID_PATH")

    def test_search_returns_file_metadata(self):
        """Search results include size and modified for files."""
        response = self.client.get("/api/v1/search/files/?q=config.json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        result = response.data["results"][0]
        self.assertEqual(result["type"], "file")
        self.assertIn("size", result)
        self.assertIn("modified", result)

    def test_search_no_results(self):
        """Search with no matches returns empty results."""
        response = self.client.get("/api/v1/search/files/?q=nonexistent123")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["results"], [])
        self.assertFalse(response.data["truncated"])

    def test_search_requires_authentication(self):
        """Search requires authentication."""
        self.client.credentials()  # Clear auth
        response = self.client.get("/api/v1/search/files/?q=readme")
        # 401 or 403 both indicate auth required
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )


class AdminSearchFilesViewTest(StormCloudAdminTestCase):
    """Tests for GET /api/v1/admin/users/{user_id}/search/files/"""

    def setUp(self):
        super().setUp()
        # Create test directory structure for target user
        user_storage = self.test_storage_root / str(self.user.account.id)
        user_storage.mkdir(parents=True, exist_ok=True)

        # Create some files for target user
        (user_storage / "secret.txt").write_text("Secret content")
        (user_storage / "notes").mkdir(exist_ok=True)
        (user_storage / "notes" / "secret-notes.md").write_text("Notes")

    def test_admin_search_user_files(self):
        """Admin can search another user's files."""
        response = self.client.get(
            f"/api/v1/admin/users/{self.user.id}/search/files/?q=secret"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertIn("target_user", response.data)
        self.assertEqual(response.data["target_user"]["id"], self.user.id)

    def test_admin_search_with_path(self):
        """Admin search respects path param."""
        response = self.client.get(
            f"/api/v1/admin/users/{self.user.id}/search/files/?q=secret&path=notes"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "secret-notes.md")

    def test_admin_search_requires_admin(self):
        """Non-admin cannot use admin search endpoint."""
        # Authenticate as regular user
        self.authenticate(api_key=self.api_key)
        response = self.client.get(
            f"/api/v1/admin/users/{self.user.id}/search/files/?q=secret"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_search_nonexistent_user(self):
        """Admin search for nonexistent user returns 404."""
        response = self.client.get("/api/v1/admin/users/99999/search/files/?q=test")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_search_requires_query(self):
        """Admin search without query returns 400."""
        response = self.client.get(f"/api/v1/admin/users/{self.user.id}/search/files/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "MISSING_QUERY")

    def test_admin_search_with_limit(self):
        """Admin search respects limit."""
        response = self.client.get(
            f"/api/v1/admin/users/{self.user.id}/search/files/?q=secret&limit=1"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertTrue(response.data["truncated"])
