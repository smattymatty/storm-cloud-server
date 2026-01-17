"""Tests for file audit logging."""

from datetime import timedelta
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone
from rest_framework import status

from accounts.tests.factories import APIKeyFactory, UserWithProfileFactory
from core.tests.base import StormCloudAdminTestCase
from storage.models import FileAuditLog, StoredFile
from storage.signals import file_action_performed

if TYPE_CHECKING:
    from accounts.typing import UserProtocol as User
else:
    User = get_user_model()


# =============================================================================
# Model Tests
# =============================================================================


class FileAuditLogModelTest(TestCase):
    """Tests for FileAuditLog model behavior."""

    def setUp(self):
        self.user1 = UserWithProfileFactory(verified=True)
        self.user2 = UserWithProfileFactory(verified=True)

    def test_create_audit_log_entry(self):
        """Can create FileAuditLog with all fields."""
        log = FileAuditLog.objects.create(
            performed_by=self.user1.account,
            target_user=self.user2.account,
            is_admin_action=True,
            action=FileAuditLog.ACTION_UPLOAD,
            path="test/file.txt",
            destination_path=None,
            paths_affected=None,
            success=True,
            error_code=None,
            error_message=None,
            ip_address="192.168.1.1",
            user_agent="TestAgent/1.0",
            file_size=1024,
            content_type="text/plain",
        )

        self.assertIsNotNone(log.id)
        self.assertEqual(log.performed_by, self.user1.account)
        self.assertEqual(log.target_user, self.user2.account)
        self.assertTrue(log.is_admin_action)
        self.assertEqual(log.action, FileAuditLog.ACTION_UPLOAD)
        self.assertEqual(log.path, "test/file.txt")
        self.assertEqual(log.file_size, 1024)

    def test_action_choices_valid(self):
        """All ACTION_* constants are valid choices."""
        valid_actions = [
            FileAuditLog.ACTION_LIST,
            FileAuditLog.ACTION_UPLOAD,
            FileAuditLog.ACTION_DOWNLOAD,
            FileAuditLog.ACTION_DELETE,
            FileAuditLog.ACTION_MOVE,
            FileAuditLog.ACTION_COPY,
            FileAuditLog.ACTION_EDIT,
            FileAuditLog.ACTION_PREVIEW,
            FileAuditLog.ACTION_CREATE_DIR,
            FileAuditLog.ACTION_BULK_DELETE,
            FileAuditLog.ACTION_BULK_MOVE,
            FileAuditLog.ACTION_BULK_COPY,
        ]

        for action in valid_actions:
            log = FileAuditLog.objects.create(
                performed_by=self.user1.account,
                target_user=self.user2.account,
                action=action,
                path="test.txt",
            )
            self.assertEqual(log.action, action)

    def test_performed_by_set_null_on_delete(self):
        """performed_by nulled when account deleted."""
        performer = UserWithProfileFactory(verified=True)
        log = FileAuditLog.objects.create(
            performed_by=performer.account,
            target_user=self.user2.account,
            action=FileAuditLog.ACTION_UPLOAD,
            path="test.txt",
        )

        performer.account.delete()
        log.refresh_from_db()

        self.assertIsNone(log.performed_by)
        self.assertEqual(log.target_user, self.user2.account)  # Still intact

    def test_target_user_set_null_on_delete(self):
        """target_user nulled when account deleted."""
        target = UserWithProfileFactory(verified=True)
        log = FileAuditLog.objects.create(
            performed_by=self.user1.account,
            target_user=target.account,
            action=FileAuditLog.ACTION_UPLOAD,
            path="test.txt",
        )

        target.account.delete()
        log.refresh_from_db()

        self.assertIsNone(log.target_user)
        self.assertEqual(log.performed_by, self.user1.account)  # Still intact

    def test_ordering_by_created_at_desc(self):
        """Default ordering is newest first."""
        log1 = FileAuditLog.objects.create(
            performed_by=self.user1.account,
            target_user=self.user2.account,
            action=FileAuditLog.ACTION_UPLOAD,
            path="first.txt",
        )
        log2 = FileAuditLog.objects.create(
            performed_by=self.user1.account,
            target_user=self.user2.account,
            action=FileAuditLog.ACTION_DOWNLOAD,
            path="second.txt",
        )

        logs = list(FileAuditLog.objects.all())
        self.assertEqual(logs[0], log2)  # Newest first
        self.assertEqual(logs[1], log1)


# =============================================================================
# Signal Tests
# =============================================================================


class FileAuditSignalTest(StormCloudAdminTestCase):
    """Tests for signal emission and handling."""

    def setUp(self):
        super().setUp()
        self.target_user = UserWithProfileFactory(verified=True)

    def _create_file_for_user(
        self, user: User, path: str, content: str = "test"
    ) -> StoredFile:
        """Create a file in user's storage."""
        storage_path = Path(self.test_storage_root) / str(user.account.id) / path
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_text(content)

        return StoredFile.objects.create(
            owner=user.account,
            path=path,
            name=Path(path).name,
            size=len(content),
            content_type="text/plain",
            is_directory=False,
            parent_path="",
            encryption_method="none",
        )

    def test_signal_creates_log_entry(self):
        """Signal handler creates FileAuditLog."""
        self._create_file_for_user(self.target_user, "signal_test.txt")

        # Trigger via admin endpoint
        response = self.client.get(f"/api/v1/admin/users/{self.target_user.id}/dirs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        log = FileAuditLog.objects.filter(
            target_user=self.target_user.account,
            action=FileAuditLog.ACTION_LIST,
        ).first()

        self.assertIsNotNone(log)

    def test_signal_captures_ip_address(self):
        """IP address captured from request."""
        self._create_file_for_user(self.target_user, "ip_test.txt")

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/dirs/",
            HTTP_X_FORWARDED_FOR="10.0.0.42",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        log = FileAuditLog.objects.filter(
            target_user=self.target_user.account,
            action=FileAuditLog.ACTION_LIST,
        ).first()

        self.assertIsNotNone(log)
        # IP should be captured (may be 127.0.0.1 in tests or the forwarded IP)
        self.assertIsNotNone(log.ip_address)

    def test_signal_captures_user_agent(self):
        """User agent captured from request."""
        self._create_file_for_user(self.target_user, "ua_test.txt")

        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/dirs/",
            HTTP_USER_AGENT="TestBrowser/1.0",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        log = FileAuditLog.objects.filter(
            target_user=self.target_user.account,
            action=FileAuditLog.ACTION_LIST,
        ).first()

        self.assertIsNotNone(log)
        self.assertEqual(log.user_agent, "TestBrowser/1.0")

    def test_admin_action_flag_set_correctly(self):
        """is_admin_action=True for admin ops."""
        self._create_file_for_user(self.target_user, "admin_flag.txt")

        response = self.client.get(f"/api/v1/admin/users/{self.target_user.id}/dirs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        log = FileAuditLog.objects.filter(
            target_user=self.target_user.account,
            action=FileAuditLog.ACTION_LIST,
        ).first()

        self.assertIsNotNone(log)
        self.assertTrue(log.is_admin_action)

    def test_performed_by_vs_target_user(self):
        """Correct user assignment."""
        self._create_file_for_user(self.target_user, "user_assign.txt")

        response = self.client.get(f"/api/v1/admin/users/{self.target_user.id}/dirs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        log = FileAuditLog.objects.filter(
            target_user=self.target_user.account,
            action=FileAuditLog.ACTION_LIST,
        ).first()

        self.assertIsNotNone(log)
        self.assertEqual(log.performed_by, self.admin.account)
        self.assertEqual(log.target_user, self.target_user.account)
        self.assertNotEqual(log.performed_by, log.target_user)

    def test_error_details_captured(self):
        """error_code/message captured on failure."""
        # Try to download a non-existent file
        response = self.client.get(
            f"/api/v1/admin/users/{self.target_user.id}/files/nonexistent.txt/download/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        log = FileAuditLog.objects.filter(
            target_user=self.target_user.account,
            action=FileAuditLog.ACTION_DOWNLOAD,
            success=False,
        ).first()

        self.assertIsNotNone(log)
        self.assertFalse(log.success)
        self.assertIsNotNone(log.error_code)


# =============================================================================
# Audit Log List Endpoint Tests
# =============================================================================


class AdminFileAuditLogListTest(StormCloudAdminTestCase):
    """Tests for GET /api/v1/admin/audit/files/"""

    def setUp(self):
        super().setUp()
        self.target_user = UserWithProfileFactory(verified=True)
        self.other_admin = UserWithProfileFactory(admin=True)

        # Create some audit logs
        self.log1 = FileAuditLog.objects.create(
            performed_by=self.admin.account,
            target_user=self.target_user.account,
            is_admin_action=True,
            action=FileAuditLog.ACTION_UPLOAD,
            path="file1.txt",
            success=True,
        )
        self.log2 = FileAuditLog.objects.create(
            performed_by=self.other_admin.account,
            target_user=self.target_user.account,
            is_admin_action=True,
            action=FileAuditLog.ACTION_DELETE,
            path="file2.txt",
            success=True,
        )
        self.log3 = FileAuditLog.objects.create(
            performed_by=self.admin.account,
            target_user=self.target_user.account,
            is_admin_action=True,
            action=FileAuditLog.ACTION_DOWNLOAD,
            path="subdir/file3.txt",
            success=False,
            error_code="FILE_NOT_FOUND",
        )

    def test_admin_list_audit_logs(self):
        """Admin can list all audit logs."""
        response = self.client.get("/api/v1/admin/audit/files/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertGreaterEqual(len(response.data["results"]), 3)

    def test_filter_by_user_id(self):
        """Filter by target_user works."""
        response = self.client.get(
            f"/api/v1/admin/audit/files/?user_id={self.target_user.account.id}"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for log in response.data["results"]:
            # Serializer returns UUID, compare directly
            self.assertEqual(log["target_user"], self.target_user.account.id)

    def test_filter_by_performed_by(self):
        """Filter by admin who performed works."""
        response = self.client.get(
            f"/api/v1/admin/audit/files/?performed_by={self.admin.account.id}"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for log in response.data["results"]:
            # Serializer returns UUID, compare directly
            self.assertEqual(log["performed_by"], self.admin.account.id)

    def test_filter_by_action(self):
        """Filter by action type works."""
        response = self.client.get("/api/v1/admin/audit/files/?action=upload")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for log in response.data["results"]:
            self.assertEqual(log["action"], "upload")

    def test_filter_by_admin_only(self):
        """admin_only=true filter works."""
        # Create a non-admin log
        FileAuditLog.objects.create(
            performed_by=self.target_user.account,
            target_user=self.target_user.account,
            is_admin_action=False,
            action=FileAuditLog.ACTION_UPLOAD,
            path="user_file.txt",
        )

        response = self.client.get("/api/v1/admin/audit/files/?admin_only=true")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for log in response.data["results"]:
            self.assertTrue(log["is_admin_action"])

    def test_filter_by_success(self):
        """success=true/false filter works."""
        response = self.client.get("/api/v1/admin/audit/files/?success=false")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for log in response.data["results"]:
            self.assertFalse(log["success"])

    def test_filter_by_path(self):
        """path contains filter works."""
        response = self.client.get("/api/v1/admin/audit/files/?path=subdir")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for log in response.data["results"]:
            self.assertIn("subdir", log["path"])

    def test_filter_by_date_range(self):
        """from/to date filters work."""
        yesterday = (timezone.now() - timedelta(days=1)).isoformat()
        tomorrow = (timezone.now() + timedelta(days=1)).isoformat()

        response = self.client.get(
            f"/api/v1/admin/audit/files/?from={yesterday}&to={tomorrow}"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data["results"]), 3)

    def test_pagination(self):
        """page/page_size work correctly."""
        # Create more logs
        for i in range(15):
            FileAuditLog.objects.create(
                performed_by=self.admin.account,
                target_user=self.target_user.account,
                action=FileAuditLog.ACTION_LIST,
                path=f"pagefile{i}.txt",
            )

        response = self.client.get("/api/v1/admin/audit/files/?page=1&page_size=5")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 5)
        self.assertIn("count", response.data)
        self.assertIn("next", response.data)

    def test_non_admin_gets_403(self):
        """Regular user cannot access."""
        regular_user = UserWithProfileFactory(verified=True)
        regular_key = APIKeyFactory(user=regular_user)
        self.authenticate(api_key=regular_key)

        response = self.client.get("/api/v1/admin/audit/files/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
