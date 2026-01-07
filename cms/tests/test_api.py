"""Tests for CMS page-file mapping API endpoints."""

from datetime import timedelta

from django.utils import timezone
from rest_framework import status

from core.tests.base import StormCloudAPITestCase
from cms.models import PageFileMapping


class MappingReportTests(StormCloudAPITestCase):
    """Tests for POST /api/v1/cms/mappings/report/"""

    def test_report_creates_mappings(self):
        """Report creates new PageFileMapping records."""
        self.authenticate()
        response = self.client.post(
            "/api/v1/cms/mappings/report/",
            {
                "page_path": "/about/",
                "file_paths": ["pages/about.md", "snippets/cta.md"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created"], 2)
        self.assertEqual(response.data["updated"], 0)
        self.assertEqual(
            PageFileMapping.objects.filter(owner=self.user).count(), 2
        )

    def test_report_updates_existing_mappings(self):
        """Report updates last_seen on existing mappings."""
        self.authenticate()

        # Create existing mapping
        old_time = timezone.now() - timedelta(hours=2)
        PageFileMapping.objects.create(
            owner=self.user,
            page_path="/about/",
            file_path="pages/about.md",
        )
        PageFileMapping.objects.filter(owner=self.user).update(last_seen=old_time)

        # Report same mapping
        response = self.client.post(
            "/api/v1/cms/mappings/report/",
            {
                "page_path": "/about/",
                "file_paths": ["pages/about.md"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created"], 0)
        self.assertEqual(response.data["updated"], 1)

        # Check last_seen was updated
        mapping = PageFileMapping.objects.get(owner=self.user)
        self.assertGreater(mapping.last_seen, old_time)

    def test_report_normalizes_page_path(self):
        """Report adds leading slash if missing."""
        self.authenticate()
        response = self.client.post(
            "/api/v1/cms/mappings/report/",
            {
                "page_path": "about/",  # No leading slash
                "file_paths": ["test.md"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["page_path"], "/about/")

    def test_report_requires_auth(self):
        """Report endpoint requires authentication."""
        response = self.client.post(
            "/api/v1/cms/mappings/report/",
            {"page_path": "/", "file_paths": ["test.md"]},
            format="json",
        )
        # DRF returns 403 when auth required but no credentials provided
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_report_requires_file_paths(self):
        """Report fails without file_paths."""
        self.authenticate()
        response = self.client.post(
            "/api/v1/cms/mappings/report/",
            {"page_path": "/about/"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_report_rejects_empty_file_paths(self):
        """Report fails with empty file_paths list."""
        self.authenticate()
        response = self.client.post(
            "/api/v1/cms/mappings/report/",
            {"page_path": "/about/", "file_paths": []},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PageListTests(StormCloudAPITestCase):
    """Tests for GET /api/v1/cms/pages/"""

    def test_list_pages_empty(self):
        """List returns empty for user with no mappings."""
        self.authenticate()
        response = self.client.get("/api/v1/cms/pages/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 0)
        self.assertEqual(response.data["pages"], [])

    def test_list_pages_with_file_counts(self):
        """List returns pages with file counts."""
        self.authenticate()

        # Create mappings
        PageFileMapping.objects.create(
            owner=self.user, page_path="/", file_path="home.md"
        )
        PageFileMapping.objects.create(
            owner=self.user, page_path="/", file_path="cta.md"
        )
        PageFileMapping.objects.create(
            owner=self.user, page_path="/about/", file_path="about.md"
        )

        response = self.client.get("/api/v1/cms/pages/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 2)

        # Find home page
        home = next(
            p for p in response.data["pages"] if p["page_path"] == "/"
        )
        self.assertEqual(home["file_count"], 2)

    def test_list_pages_filter_stale(self):
        """Filter to only stale pages."""
        self.authenticate()

        # Create fresh and stale mappings
        PageFileMapping.objects.create(
            owner=self.user, page_path="/", file_path="home.md"
        )
        stale = PageFileMapping.objects.create(
            owner=self.user, page_path="/about/", file_path="about.md"
        )

        # Make /about/ stale
        old_time = timezone.now() - timedelta(hours=48)
        PageFileMapping.objects.filter(pk=stale.pk).update(last_seen=old_time)

        response = self.client.get("/api/v1/cms/pages/?stale=true")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 1)
        self.assertEqual(response.data["pages"][0]["page_path"], "/about/")
        self.assertTrue(response.data["pages"][0]["is_stale"])

    def test_list_pages_sort_by_path(self):
        """Sort pages by path."""
        self.authenticate()

        PageFileMapping.objects.create(
            owner=self.user, page_path="/zebra/", file_path="z.md"
        )
        PageFileMapping.objects.create(
            owner=self.user, page_path="/apple/", file_path="a.md"
        )

        response = self.client.get("/api/v1/cms/pages/?sort=path&order=asc")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        paths = [p["page_path"] for p in response.data["pages"]]
        self.assertEqual(paths, ["/apple/", "/zebra/"])


class PageDetailTests(StormCloudAPITestCase):
    """Tests for GET/DELETE /api/v1/cms/pages/{path}/"""

    def test_get_page_detail(self):
        """Get files for a page."""
        self.authenticate()

        PageFileMapping.objects.create(
            owner=self.user, page_path="/about/", file_path="pages/about.md"
        )
        PageFileMapping.objects.create(
            owner=self.user, page_path="/about/", file_path="snippets/cta.md"
        )

        response = self.client.get("/api/v1/cms/pages/about//")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["page_path"], "/about/")
        self.assertEqual(len(response.data["files"]), 2)

    def test_get_page_detail_404(self):
        """Get returns 404 for unknown page."""
        self.authenticate()
        response = self.client.get("/api/v1/cms/pages/unknown//")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_page_mappings(self):
        """Delete all mappings for a page."""
        self.authenticate()

        PageFileMapping.objects.create(
            owner=self.user, page_path="/old/", file_path="old1.md"
        )
        PageFileMapping.objects.create(
            owner=self.user, page_path="/old/", file_path="old2.md"
        )

        response = self.client.delete("/api/v1/cms/pages/old//")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["deleted"], 2)
        self.assertEqual(
            PageFileMapping.objects.filter(owner=self.user).count(), 0
        )

    def test_delete_page_404(self):
        """Delete returns 404 for unknown page."""
        self.authenticate()
        response = self.client.delete("/api/v1/cms/pages/unknown//")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class FileDetailTests(StormCloudAPITestCase):
    """Tests for GET /api/v1/cms/files/{path}/pages/"""

    def test_get_pages_using_file(self):
        """Get all pages using a file."""
        self.authenticate()

        PageFileMapping.objects.create(
            owner=self.user, page_path="/", file_path="snippets/cta.md"
        )
        PageFileMapping.objects.create(
            owner=self.user, page_path="/about/", file_path="snippets/cta.md"
        )
        PageFileMapping.objects.create(
            owner=self.user, page_path="/services/", file_path="snippets/cta.md"
        )

        response = self.client.get("/api/v1/cms/files/snippets/cta.md/pages/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["file_path"], "snippets/cta.md")
        self.assertEqual(response.data["page_count"], 3)

    def test_get_pages_using_file_404(self):
        """Get returns 404 for unknown file."""
        self.authenticate()
        response = self.client.get("/api/v1/cms/files/unknown.md/pages/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class StaleCleanupTests(StormCloudAPITestCase):
    """Tests for POST /api/v1/cms/cleanup/"""

    def test_cleanup_deletes_stale_mappings(self):
        """Cleanup deletes mappings older than threshold."""
        self.authenticate()

        # Create fresh and stale mappings
        fresh = PageFileMapping.objects.create(
            owner=self.user, page_path="/", file_path="fresh.md"
        )
        stale = PageFileMapping.objects.create(
            owner=self.user, page_path="/old/", file_path="old.md"
        )

        # Make one stale (8 days old)
        old_time = timezone.now() - timedelta(hours=200)
        PageFileMapping.objects.filter(pk=stale.pk).update(last_seen=old_time)

        response = self.client.post(
            "/api/v1/cms/cleanup/",
            {"hours": 168},  # 7 days
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["deleted"], 1)
        self.assertEqual(response.data["threshold_hours"], 168)

        # Fresh one should remain
        self.assertEqual(PageFileMapping.objects.count(), 1)
        self.assertTrue(PageFileMapping.objects.filter(pk=fresh.pk).exists())

    def test_cleanup_rejects_low_threshold(self):
        """Cleanup rejects threshold below 24 hours."""
        self.authenticate()
        response = self.client.post(
            "/api/v1/cms/cleanup/",
            {"hours": 12},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cleanup_default_threshold(self):
        """Cleanup uses 168 hours (7 days) by default."""
        self.authenticate()
        response = self.client.post("/api/v1/cms/cleanup/", format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["threshold_hours"], 168)


class StalenessModelTests(StormCloudAPITestCase):
    """Tests for PageFileMapping staleness methods."""

    def test_is_stale_false_for_fresh(self):
        """is_stale returns False for fresh mappings."""
        self.authenticate()
        mapping = PageFileMapping.objects.create(
            owner=self.user, page_path="/", file_path="test.md"
        )
        self.assertFalse(mapping.is_stale)

    def test_is_stale_true_after_24h(self):
        """is_stale returns True after 24 hours."""
        self.authenticate()
        mapping = PageFileMapping.objects.create(
            owner=self.user, page_path="/", file_path="test.md"
        )

        # Make stale
        old_time = timezone.now() - timedelta(hours=25)
        PageFileMapping.objects.filter(pk=mapping.pk).update(last_seen=old_time)
        mapping.refresh_from_db()

        self.assertTrue(mapping.is_stale)

    def test_staleness_hours(self):
        """staleness_hours returns correct hours for stale mapping."""
        self.authenticate()
        mapping = PageFileMapping.objects.create(
            owner=self.user, page_path="/", file_path="test.md"
        )

        # Make 48 hours stale
        old_time = timezone.now() - timedelta(hours=48)
        PageFileMapping.objects.filter(pk=mapping.pk).update(last_seen=old_time)
        mapping.refresh_from_db()

        self.assertIsNotNone(mapping.staleness_hours)
        self.assertGreaterEqual(mapping.staleness_hours, 47)  # Allow for test timing

    def test_staleness_hours_none_for_fresh(self):
        """staleness_hours returns None for fresh mapping."""
        self.authenticate()
        mapping = PageFileMapping.objects.create(
            owner=self.user, page_path="/", file_path="test.md"
        )
        self.assertIsNone(mapping.staleness_hours)


class MarkdownPreviewTests(StormCloudAPITestCase):
    """Tests for POST /api/v1/cms/preview/"""

    def test_preview_renders_markdown(self):
        """Preview converts markdown to HTML."""
        self.authenticate()
        response = self.client.post(
            "/api/v1/cms/preview/",
            {"content": "# Hello World"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("<h1", response.data["html"])
        self.assertIn("Hello World", response.data["html"])

    def test_preview_renders_spellblocks(self):
        """Preview renders SpellBlock syntax."""
        self.authenticate()
        response = self.client.post(
            "/api/v1/cms/preview/",
            {"content": "{~ alert type=\"info\" ~}\nTest alert\n{~~}"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # SpellBlock should produce some HTML output
        self.assertIn("html", response.data)
        self.assertTrue(len(response.data["html"]) > 0)

    def test_preview_empty_content(self):
        """Preview handles empty content."""
        self.authenticate()
        response = self.client.post(
            "/api/v1/cms/preview/",
            {"content": ""},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("html", response.data)

    def test_preview_missing_content(self):
        """Preview handles missing content field."""
        self.authenticate()
        response = self.client.post(
            "/api/v1/cms/preview/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("html", response.data)

    def test_preview_requires_auth(self):
        """Preview endpoint requires authentication."""
        response = self.client.post(
            "/api/v1/cms/preview/",
            {"content": "# Test"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
