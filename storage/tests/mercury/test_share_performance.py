"""Performance tests for share link endpoints using Django Mercury."""

from io import BytesIO
from django.test import override_settings
from rest_framework.test import APITestCase
from django_mercury import monitor
from accounts.tests.factories import UserWithProfileFactory, APIKeyFactory
from storage.models import ShareLink
from storage.tests.factories import ShareLinkFactory


@override_settings(STORAGE_ENCRYPTION_METHOD="none")
class PublicShareAccessPerformance(APITestCase):
    """Performance baselines for public share access."""

    def setUp(self):
        super().setUp()
        self.user = UserWithProfileFactory(verified=True)
        # Explicitly set created_by so APIKeyUser.account works
        self.api_key = APIKeyFactory(
            organization=self.user.account.organization,
            created_by=self.user.account,
        )

        # Upload actual file and create share link
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.api_key.key}")
        test_file = BytesIO(b"performance test content")
        test_file.name = "perf.txt"
        self.client.post("/api/v1/user/files/perf.txt/upload/", {"file": test_file})

        # Create share link via API
        response = self.client.post("/api/v1/shares/", {"file_path": "perf.txt"})
        self.share = ShareLink.objects.get(id=response.data["id"])

        # Clear auth for public access test
        self.client.credentials()

    def test_public_download_under_50ms(self):
        """Public file download initiation should be under 50ms."""
        with monitor(response_time_ms=50, query_count=6) as result:
            response = self.client.get(f"/api/v1/public/{self.share.token}/download/")
        result.explain()

        self.assertEqual(response.status_code, 200)


@override_settings(STORAGE_ENCRYPTION_METHOD="none")
class ShareLinkListingPerformance(APITestCase):
    """Performance baselines for share link listing."""

    def setUp(self):
        super().setUp()
        self.user = UserWithProfileFactory(verified=True)
        # Explicitly set created_by so APIKeyUser.account works
        self.api_key = APIKeyFactory(
            organization=self.user.account.organization,
            created_by=self.user.account,
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.api_key.key}")

        # Create 50 share links
        ShareLinkFactory.create_batch(50, owner=self.user.account)

    def test_list_50_shares_under_100ms(self):
        """Listing 50 share links should be under 100ms with minimal queries."""
        with monitor(response_time_ms=100, query_count=5) as result:
            response = self.client.get("/api/v1/shares/")
        result.explain()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 50)
