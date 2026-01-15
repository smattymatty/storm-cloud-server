"""Tests for file content preview and edit endpoints."""

from io import BytesIO

from django.test import override_settings
from rest_framework import status

from core.tests.base import StormCloudAPITestCase
from storage.models import StoredFile


class FileContentPreviewTest(StormCloudAPITestCase):
    """GET /api/v1/files/{path}/content/ - Preview file content"""

    def test_preview_text_file_succeeds(self):
        """Preview should return raw content for text files."""
        self.authenticate()

        # Upload a text file
        content = b"# Hello World\n\nThis is a test."
        test_file = BytesIO(content)
        test_file.name = "readme.md"
        self.client.post("/api/v1/files/readme.md/upload/", {"file": test_file})

        # Preview it
        response = self.client.get("/api/v1/files/readme.md/content/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.content, content)
        self.assertIn("text/plain", response["Content-Type"])
        self.assertEqual(response["X-Content-Type-Original"], "text/markdown")

    def test_preview_python_file_succeeds(self):
        """Python files should be previewable."""
        self.authenticate()

        content = b'def hello():\n    print("Hello")\n'
        test_file = BytesIO(content)
        test_file.name = "script.py"
        self.client.post("/api/v1/files/script.py/upload/", {"file": test_file})

        response = self.client.get("/api/v1/files/script.py/content/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.content, content)

    def test_preview_json_file_succeeds(self):
        """JSON files should be previewable."""
        self.authenticate()

        content = b'{"key": "value", "number": 42}'
        test_file = BytesIO(content)
        test_file.name = "config.json"
        self.client.post("/api/v1/files/config.json/upload/", {"file": test_file})

        response = self.client.get("/api/v1/files/config.json/content/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.content, content)

    def test_preview_binary_file_returns_400(self):
        """Binary files should return 400 error."""
        self.authenticate()

        # Upload a fake PNG file (PNG magic bytes)
        content = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
        test_file = BytesIO(content)
        test_file.name = "image.png"
        self.client.post("/api/v1/files/image.png/upload/", {"file": test_file})

        response = self.client.get("/api/v1/files/image.png/content/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "NOT_TEXT_FILE")
        self.assertIn("recovery", response.data["error"])

    def test_preview_nonexistent_file_returns_404(self):
        """Previewing non-existent file should return 404."""
        self.authenticate()

        response = self.client.get("/api/v1/files/nonexistent.txt/content/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "FILE_NOT_FOUND")

    def test_preview_directory_returns_400(self):
        """Previewing a directory should return 400."""
        self.authenticate()

        # Create a directory
        self.client.post("/api/v1/dirs/mydir/create/")

        response = self.client.get("/api/v1/files/mydir/content/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "PATH_IS_DIRECTORY")

    @override_settings(STORMCLOUD_MAX_PREVIEW_SIZE_MB=0)
    def test_preview_large_file_returns_413(self):
        """Files exceeding size limit should return 413."""
        self.authenticate()

        # Upload any file - with limit set to 0, all files are "too large"
        content = b"any content"
        test_file = BytesIO(content)
        test_file.name = "large.txt"
        self.client.post("/api/v1/files/large.txt/upload/", {"file": test_file})

        response = self.client.get("/api/v1/files/large.txt/content/")

        self.assertEqual(response.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        self.assertEqual(response.data["error"]["code"], "FILE_TOO_LARGE")

    def test_preview_path_traversal_blocked(self):
        """Path traversal should be blocked."""
        self.authenticate()

        response = self.client.get("/api/v1/files/../etc/passwd/content/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "INVALID_PATH")

    def test_preview_requires_authentication(self):
        """Preview should require authentication."""
        # Don't authenticate

        response = self.client.get("/api/v1/files/test.txt/content/")

        # DRF returns 403 when no credentials provided
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )


class FileContentEditTest(StormCloudAPITestCase):
    """PUT /api/v1/files/{path}/content/ - Edit file content"""

    def setUp(self):
        super().setUp()
        self.authenticate()

        # Create a file to edit
        test_file = BytesIO(b"original content")
        test_file.name = "editable.txt"
        self.client.post("/api/v1/files/editable.txt/upload/", {"file": test_file})

    def test_edit_file_succeeds(self):
        """Editing should update file content."""
        new_content = b"updated content"

        response = self.client.put(
            "/api/v1/files/editable.txt/content/",
            data=new_content,
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["size"], len(new_content))
        self.assertEqual(response.data["path"], "editable.txt")

        # Verify content changed
        preview = self.client.get("/api/v1/files/editable.txt/content/")
        self.assertEqual(preview.content, new_content)

    def test_edit_updates_database_size(self):
        """Edit should update size in database."""
        new_content = b"x" * 100

        self.client.put(
            "/api/v1/files/editable.txt/content/",
            data=new_content,
            content_type="text/plain",
        )

        stored = StoredFile.objects.get(owner=self.user.account, path="editable.txt")
        self.assertEqual(stored.size, 100)

    def test_edit_nonexistent_file_returns_404(self):
        """Editing non-existent file should return 404."""
        response = self.client.put(
            "/api/v1/files/nonexistent.txt/content/",
            data=b"content",
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "FILE_NOT_FOUND")
        self.assertIn("recovery", response.data["error"])

    def test_edit_directory_returns_400(self):
        """Editing a directory should return 400."""
        # Create a directory
        self.client.post("/api/v1/dirs/mydir/create/")

        response = self.client.put(
            "/api/v1/files/mydir/content/",
            data=b"content",
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "PATH_IS_DIRECTORY")

    def test_edit_respects_quota(self):
        """Edit should check quota before saving."""
        # Set very low quota (10 bytes)
        self.user.account.storage_quota_bytes = 10
        self.user.account.save()

        response = self.client.put(
            "/api/v1/files/editable.txt/content/",
            data=b"x" * 100,
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, status.HTTP_507_INSUFFICIENT_STORAGE)
        self.assertEqual(response.data["error"]["code"], "QUOTA_EXCEEDED")

    def test_edit_path_traversal_blocked(self):
        """Path traversal should be blocked."""
        response = self.client.put(
            "/api/v1/files/../etc/passwd/content/",
            data=b"hacked",
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "INVALID_PATH")

    def test_edit_requires_authentication(self):
        """Edit should require authentication."""
        # Remove authentication
        self.client.credentials()

        response = self.client.put(
            "/api/v1/files/editable.txt/content/",
            data=b"new content",
            content_type="text/plain",
        )

        # DRF returns 403 when no credentials provided
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_edit_with_empty_content(self):
        """Editing with empty content should create empty file."""
        response = self.client.put(
            "/api/v1/files/editable.txt/content/",
            data=b"",
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["size"], 0)

        # Verify content is empty
        preview = self.client.get("/api/v1/files/editable.txt/content/")
        self.assertEqual(preview.content, b"")

    def test_edit_nested_file(self):
        """Editing a file in a nested directory should work."""
        # Create nested file
        self.client.post("/api/v1/dirs/folder/create/")
        test_file = BytesIO(b"nested content")
        test_file.name = "nested.txt"
        self.client.post("/api/v1/files/folder/nested.txt/upload/", {"file": test_file})

        # Edit it
        new_content = b"updated nested content"
        response = self.client.put(
            "/api/v1/files/folder/nested.txt/content/",
            data=new_content,
            content_type="text/plain",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify
        preview = self.client.get("/api/v1/files/folder/nested.txt/content/")
        self.assertEqual(preview.content, new_content)
