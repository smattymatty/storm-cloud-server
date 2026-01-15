"""Tests for share link API endpoints."""

from io import BytesIO
from unittest.mock import patch
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from core.tests.base import StormCloudAPITestCase
from storage.models import ShareLink
from storage.tests.factories import ShareLinkFactory
from accounts.tests.factories import UserWithProfileFactory


class ShareLinkCreationTest(StormCloudAPITestCase):
    """POST /api/v1/shares/ - Create share links"""

    def test_create_share_link_for_existing_file(self):
        """Creating share link for existing file should succeed."""
        self.authenticate()

        # Upload a file first
        test_file = BytesIO(b"test content for sharing")
        test_file.name = "shareable.txt"
        upload_response = self.client.post(
            "/api/v1/files/shareable.txt/upload/", {"file": test_file}
        )
        self.assertEqual(upload_response.status_code, status.HTTP_201_CREATED)

        # Create share link
        response = self.client.post(
            "/api/v1/shares/", {"file_path": "shareable.txt", "expiry_days": 7}
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["file_path"], "shareable.txt")
        self.assertEqual(response.data["expiry_days"], 7)
        self.assertIn("token", response.data)
        self.assertIn("url", response.data)
        self.assertIsNotNone(response.data["expires_at"])
        self.assertTrue(response.data["is_active"])
        self.assertFalse(response.data["has_password"])

    def test_create_share_link_for_nonexistent_file(self):
        """Creating share link for nonexistent file should return 404."""
        self.authenticate()

        response = self.client.post(
            "/api/v1/shares/", {"file_path": "nonexistent.txt", "expiry_days": 7}
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "FILE_NOT_FOUND")

    def test_create_share_link_with_custom_slug(self):
        """Creating share link with valid custom slug should succeed."""
        self.authenticate()

        # Upload file
        test_file = BytesIO(b"custom slug content")
        test_file.name = "custom.txt"
        self.client.post("/api/v1/files/custom.txt/upload/", {"file": test_file})

        # Create share with custom slug
        response = self.client.post(
            "/api/v1/shares/",
            {
                "file_path": "custom.txt",
                "custom_slug": "my-awesome-file",
                "expiry_days": 7,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["custom_slug"], "my-awesome-file")
        self.assertIn("my-awesome-file", response.data["url"])

    def test_create_share_link_with_invalid_slug(self):
        """Creating share link with invalid slug should return 400."""
        self.authenticate()

        # Upload file
        test_file = BytesIO(b"invalid slug test")
        test_file.name = "test.txt"
        self.client.post("/api/v1/files/test.txt/upload/", {"file": test_file})

        # Test invalid characters
        response = self.client.post(
            "/api/v1/shares/", {"file_path": "test.txt", "custom_slug": "invalid slug!"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Test too short
        response = self.client.post(
            "/api/v1/shares/", {"file_path": "test.txt", "custom_slug": "ab"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_share_link_with_duplicate_slug(self):
        """Creating share link with duplicate slug should return 400."""
        self.authenticate()

        # Upload files
        for filename in ["file1.txt", "file2.txt"]:
            test_file = BytesIO(b"content")
            test_file.name = filename
            self.client.post(f"/api/v1/files/{filename}/upload/", {"file": test_file})

        # Create first share link
        self.client.post(
            "/api/v1/shares/",
            {"file_path": "file1.txt", "custom_slug": "duplicate-slug"},
        )

        # Try to create second with same slug
        response = self.client.post(
            "/api/v1/shares/",
            {"file_path": "file2.txt", "custom_slug": "duplicate-slug"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("slug", str(response.data).lower())

    def test_create_share_link_with_password(self):
        """Creating share link with password should hash it."""
        self.authenticate()

        # Upload file
        test_file = BytesIO(b"password protected")
        test_file.name = "secret.txt"
        self.client.post("/api/v1/files/secret.txt/upload/", {"file": test_file})

        # Create password-protected share
        response = self.client.post(
            "/api/v1/shares/",
            {"file_path": "secret.txt", "password": "supersecret123", "expiry_days": 7},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["has_password"])

        # Verify password is hashed in DB
        share_link = ShareLink.objects.get(id=response.data["id"])
        self.assertIsNotNone(share_link.password_hash)
        self.assertNotEqual(share_link.password_hash, "supersecret123")
        self.assertTrue(share_link.check_password("supersecret123"))

    def test_create_share_link_expiry_calculation(self):
        """Share link expiry should be calculated correctly."""
        self.authenticate()

        # Upload file
        test_file = BytesIO(b"expiry test")
        test_file.name = "expiry.txt"
        self.client.post("/api/v1/files/expiry.txt/upload/", {"file": test_file})

        # Create share with 30 day expiry
        before_creation = timezone.now()
        response = self.client.post(
            "/api/v1/shares/", {"file_path": "expiry.txt", "expiry_days": 30}
        )
        after_creation = timezone.now()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify expires_at is approximately 30 days from now
        expires_at = timezone.datetime.fromisoformat(
            response.data["expires_at"].replace("Z", "+00:00")
        )
        expected_min = before_creation + timedelta(days=30)
        expected_max = after_creation + timedelta(days=30)

        self.assertGreaterEqual(expires_at, expected_min)
        self.assertLessEqual(expires_at, expected_max)

    def test_create_unlimited_share_link(self):
        """Creating unlimited share link should set expires_at to null."""
        self.authenticate()

        # Upload file
        test_file = BytesIO(b"unlimited content")
        test_file.name = "unlimited.txt"
        self.client.post("/api/v1/files/unlimited.txt/upload/", {"file": test_file})

        # Create unlimited share
        response = self.client.post(
            "/api/v1/shares/",
            {
                "file_path": "unlimited.txt",
                "expiry_days": 0,  # 0 = unlimited
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["expiry_days"], 0)
        self.assertIsNone(response.data["expires_at"])

    def test_create_share_link_unauthenticated(self):
        """Creating share link without authentication should return 401."""
        response = self.client.post(
            "/api/v1/shares/", {"file_path": "test.txt", "expiry_days": 7}
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ShareLinkListDetailTest(StormCloudAPITestCase):
    """GET /api/v1/shares/ and GET /api/v1/shares/{id}/"""

    def test_list_share_links_returns_user_links_only(self):
        """List endpoint should return only current user's share links."""
        self.authenticate()

        # Upload and create shares for current user
        for i in range(3):
            test_file = BytesIO(f"content {i}".encode())
            test_file.name = f"file{i}.txt"
            self.client.post(f"/api/v1/files/file{i}.txt/upload/", {"file": test_file})
            self.client.post("/api/v1/shares/", {"file_path": f"file{i}.txt"})

        # Create another user with shares
        other_user = UserWithProfileFactory(verified=True)
        ShareLinkFactory.create_batch(2, owner=other_user.account)

        # List current user's shares
        response = self.client.get("/api/v1/shares/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)
        for share in response.data:
            self.assertEqual(share["owner"], self.user.account.id)

    def test_list_share_links_unauthenticated(self):
        """List endpoint without authentication should return 403."""
        response = self.client.get("/api/v1/shares/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_share_link_detail(self):
        """Get share link detail should return full information."""
        self.authenticate()

        # Upload and create share
        test_file = BytesIO(b"detail test")
        test_file.name = "detail.txt"
        self.client.post("/api/v1/files/detail.txt/upload/", {"file": test_file})
        create_response = self.client.post(
            "/api/v1/shares/", {"file_path": "detail.txt"}
        )
        share_id = create_response.data["id"]

        # Get detail
        response = self.client.get(f"/api/v1/shares/{share_id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], share_id)
        self.assertEqual(response.data["file_path"], "detail.txt")
        self.assertIn("token", response.data)
        self.assertIn("url", response.data)

    def test_get_other_user_share_link_returns_404(self):
        """Getting another user's share link should return 404."""
        self.authenticate()

        # Create share for other user
        other_user = UserWithProfileFactory(verified=True)
        other_share = ShareLinkFactory(owner=other_user.account)

        # Try to access it
        response = self.client.get(f"/api/v1/shares/{other_share.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_includes_expired_and_active_links(self):
        """List should include both expired and active links."""
        self.authenticate()

        # Create active share
        active = ShareLinkFactory(owner=self.user.account, expiry_days=7)

        # Create expired share
        expired = ShareLinkFactory(owner=self.user.account, expiry_days=7)
        expired.expires_at = timezone.now() - timedelta(days=1)
        expired.save(update_fields=["expires_at"])

        response = self.client.get("/api/v1/shares/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

        # Verify is_expired is correctly calculated
        share_ids = {share["id"]: share for share in response.data}
        self.assertFalse(share_ids[str(active.id)]["is_expired"])
        self.assertTrue(share_ids[str(expired.id)]["is_expired"])


class ShareLinkRevocationTest(StormCloudAPITestCase):
    """DELETE /api/v1/shares/{id}/ - Revoke share links"""

    def test_revoke_share_link_soft_deletes(self):
        """Revoking share link should soft delete (set is_active=False)."""
        self.authenticate()

        # Create share
        share = ShareLinkFactory(owner=self.user.account)

        # Revoke it
        response = self.client.delete(f"/api/v1/shares/{share.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Share link revoked")

        # Verify soft delete in DB
        share.refresh_from_db()
        self.assertFalse(share.is_active)

    def test_revoke_other_user_share_returns_404(self):
        """Revoking another user's share link should return 404."""
        self.authenticate()

        # Create share for other user
        other_user = UserWithProfileFactory(verified=True)
        other_share = ShareLinkFactory(owner=other_user.account)

        # Try to revoke it
        response = self.client.delete(f"/api/v1/shares/{other_share.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Verify it wasn't revoked
        other_share.refresh_from_db()
        self.assertTrue(other_share.is_active)

    def test_access_revoked_share_returns_404(self):
        """Accessing revoked share link via public endpoint should return 404."""
        from storage.tests.factories import StoredFileFactory

        # Create file record
        StoredFileFactory(owner=self.user.account, path="revoked-file.txt")

        # Create and revoke share
        share = ShareLinkFactory(
            owner=self.user.account, file_path="revoked-file.txt", is_active=False
        )

        # Try to access via public endpoint
        response = self.client.get(f"/api/v1/public/{share.token}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "SHARE_NOT_FOUND")


class PublicShareAccessTest(StormCloudAPITestCase):
    """GET /api/v1/public/{token}/ and /api/v1/public/{token}/download/"""

    def test_public_info_access_by_token(self):
        """Public info endpoint should work with UUID token."""
        # Create file and share
        self.authenticate()
        test_file = BytesIO(b"public content")
        test_file.name = "public.txt"
        self.client.post("/api/v1/files/public.txt/upload/", {"file": test_file})
        create_response = self.client.post(
            "/api/v1/shares/", {"file_path": "public.txt"}
        )
        token = create_response.data["token"]

        # Access without authentication
        self.client.credentials()
        response = self.client.get(f"/api/v1/public/{token}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "public.txt")
        self.assertIn("size", response.data)
        self.assertIn("content_type", response.data)
        self.assertFalse(response.data["requires_password"])
        self.assertIn("download_url", response.data)

    def test_public_info_access_by_custom_slug(self):
        """Public info endpoint should work with custom slug."""
        # Create file and share with custom slug
        self.authenticate()
        test_file = BytesIO(b"slug content")
        test_file.name = "slug.txt"
        self.client.post("/api/v1/files/slug.txt/upload/", {"file": test_file})
        self.client.post(
            "/api/v1/shares/",
            {"file_path": "slug.txt", "custom_slug": "my-custom-slug"},
        )

        # Access by slug
        self.client.credentials()
        response = self.client.get("/api/v1/public/my-custom-slug/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "slug.txt")

    def test_public_access_expired_share_returns_404(self):
        """Accessing expired share should return 404."""
        from storage.tests.factories import StoredFileFactory

        # Create file record (needed for share to work)
        stored_file = StoredFileFactory(owner=self.user.account, path="expired-file.txt")

        # Create expired share
        share = ShareLinkFactory(
            owner=self.user.account, stored_file=stored_file, expiry_days=7
        )
        share.expires_at = timezone.now() - timedelta(days=1)
        share.save(update_fields=["expires_at"])

        response = self.client.get(f"/api/v1/public/{share.token}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "SHARE_NOT_FOUND")

    def test_public_access_nonexistent_token_returns_404(self):
        """Accessing nonexistent token should return 404."""
        response = self.client.get("/api/v1/public/nonexistent-token-12345/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_public_password_protected_info(self):
        """Password-protected share should require password for info."""
        # Create password-protected share
        self.authenticate()
        test_file = BytesIO(b"secret content")
        test_file.name = "secret.txt"
        self.client.post("/api/v1/files/secret.txt/upload/", {"file": test_file})
        create_response = self.client.post(
            "/api/v1/shares/", {"file_path": "secret.txt", "password": "secret123"}
        )
        token = create_response.data["token"]

        # Try without password
        self.client.credentials()
        response = self.client.get(f"/api/v1/public/{token}/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"]["code"], "PASSWORD_REQUIRED")

    def test_public_password_protected_correct_password(self):
        """Password-protected share should work with correct password."""
        # Create password-protected share
        self.authenticate()
        test_file = BytesIO(b"secret content")
        test_file.name = "secret.txt"
        self.client.post("/api/v1/files/secret.txt/upload/", {"file": test_file})
        create_response = self.client.post(
            "/api/v1/shares/", {"file_path": "secret.txt", "password": "secret123"}
        )
        token = create_response.data["token"]

        # Access with correct password
        self.client.credentials()
        response = self.client.get(
            f"/api/v1/public/{token}/", HTTP_X_SHARE_PASSWORD="secret123"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "secret.txt")

    def test_public_password_protected_wrong_password(self):
        """Password-protected share should reject wrong password."""
        # Create password-protected share
        self.authenticate()
        test_file = BytesIO(b"secret content")
        test_file.name = "secret.txt"
        self.client.post("/api/v1/files/secret.txt/upload/", {"file": test_file})
        create_response = self.client.post(
            "/api/v1/shares/", {"file_path": "secret.txt", "password": "secret123"}
        )
        token = create_response.data["token"]

        # Try with wrong password
        self.client.credentials()
        response = self.client.get(
            f"/api/v1/public/{token}/", HTTP_X_SHARE_PASSWORD="wrongpassword"
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"]["code"], "INVALID_PASSWORD")

    def test_public_download_streams_file(self):
        """Public download endpoint should stream file content."""
        # Create share
        self.authenticate()
        file_content = b"downloadable content for testing"
        test_file = BytesIO(file_content)
        test_file.name = "download.txt"
        self.client.post("/api/v1/files/download.txt/upload/", {"file": test_file})
        create_response = self.client.post(
            "/api/v1/shares/", {"file_path": "download.txt"}
        )
        token = create_response.data["token"]

        # Download without authentication
        self.client.credentials()
        response = self.client.get(f"/api/v1/public/{token}/download/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(b"".join(response.streaming_content), file_content)
        self.assertEqual(response["Content-Type"], "text/plain")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_public_download_password_protected(self):
        """Public download should require password for protected shares."""
        # Create password-protected share
        self.authenticate()
        test_file = BytesIO(b"secret download")
        test_file.name = "secret-dl.txt"
        self.client.post("/api/v1/files/secret-dl.txt/upload/", {"file": test_file})
        create_response = self.client.post(
            "/api/v1/shares/", {"file_path": "secret-dl.txt", "password": "download123"}
        )
        token = create_response.data["token"]

        # Try download without password
        self.client.credentials()
        response = self.client.get(f"/api/v1/public/{token}/download/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # Download with correct password
        response = self.client.get(
            f"/api/v1/public/{token}/download/", HTTP_X_SHARE_PASSWORD="download123"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(b"".join(response.streaming_content), b"secret download")

    def test_public_access_increments_analytics(self):
        """Public access should increment view_count and update last_accessed_at."""
        # Create share
        self.authenticate()
        test_file = BytesIO(b"analytics test")
        test_file.name = "analytics.txt"
        self.client.post("/api/v1/files/analytics.txt/upload/", {"file": test_file})
        create_response = self.client.post(
            "/api/v1/shares/", {"file_path": "analytics.txt"}
        )
        token = create_response.data["token"]
        share_id = create_response.data["id"]

        # Initial state
        share = ShareLink.objects.get(id=share_id)
        self.assertEqual(share.view_count, 0)
        self.assertEqual(share.download_count, 0)
        self.assertIsNone(share.last_accessed_at)

        # Access the share
        self.client.credentials()
        before_access = timezone.now()
        self.client.get(f"/api/v1/public/{token}/")
        after_access = timezone.now()

        # Verify analytics updated
        share.refresh_from_db()
        self.assertEqual(share.view_count, 1)
        self.assertEqual(share.download_count, 0)  # No download yet
        self.assertIsNotNone(share.last_accessed_at)
        assert share.last_accessed_at is not None  # Type narrowing for mypy
        self.assertGreaterEqual(share.last_accessed_at, before_access)
        self.assertLessEqual(share.last_accessed_at, after_access)

        # Access again
        self.client.get(f"/api/v1/public/{token}/")
        share.refresh_from_db()
        self.assertEqual(share.view_count, 2)
        self.assertEqual(share.download_count, 0)

    def test_public_download_increments_analytics(self):
        """Public download should increment download_count, not view_count."""
        # Create share
        self.authenticate()
        test_file = BytesIO(b"download analytics")
        test_file.name = "dl-analytics.txt"
        self.client.post("/api/v1/files/dl-analytics.txt/upload/", {"file": test_file})
        create_response = self.client.post(
            "/api/v1/shares/", {"file_path": "dl-analytics.txt"}
        )
        token = create_response.data["token"]
        share_id = create_response.data["id"]

        # Download the file
        self.client.credentials()
        self.client.get(f"/api/v1/public/{token}/download/")

        # Verify analytics updated - only download_count, not view_count
        share = ShareLink.objects.get(id=share_id)
        self.assertEqual(share.view_count, 0)
        self.assertEqual(share.download_count, 1)
        self.assertIsNotNone(share.last_accessed_at)

    @patch("core.throttling.PublicShareRateThrottle.get_rate")
    def test_public_endpoints_are_throttled(self, mock_get_rate):
        """Public endpoints should have throttling enabled."""
        # This test verifies throttle classes are attached
        # Actual rate limiting is tested in integration tests
        from storage.api import PublicShareInfoView, PublicShareDownloadView

        # Verify throttle classes are configured
        self.assertIn(
            "PublicShareRateThrottle",
            [t.__name__ for t in PublicShareInfoView.throttle_classes],
        )
        self.assertIn(
            "PublicShareDownloadRateThrottle",
            [t.__name__ for t in PublicShareDownloadView.throttle_classes],
        )
