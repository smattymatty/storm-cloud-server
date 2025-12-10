"""Base test classes for Storm Cloud API tests."""

import shutil
from pathlib import Path
from django.conf import settings
from django.test import override_settings
from rest_framework.test import APITestCase


class StormCloudAPITestCase(APITestCase):
    """
    Base test case with common setup for Storm Cloud tests.

    Automatically configures isolated test storage and cleans up after tests.
    """

    @classmethod
    def setUpClass(cls):
        """Set up test storage directory."""
        super().setUpClass()
        cls.test_storage_root = settings.BASE_DIR / 'storage_root_test'
        cls.test_storage_root.mkdir(exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        """Clean up test storage directory."""
        super().tearDownClass()
        if cls.test_storage_root.exists():
            shutil.rmtree(cls.test_storage_root)

    def setUp(self):
        super().setUp()
        # Import here to avoid circular imports
        from accounts.tests.factories import UserWithProfileFactory, APIKeyFactory

        self.user = UserWithProfileFactory(verified=True)
        self.api_key = APIKeyFactory(user=self.user)

        # Use test storage root for this test run
        # Disable throttling during tests to prevent rate limit failures
        rest_framework_settings = dict(settings.REST_FRAMEWORK)
        rest_framework_settings['DEFAULT_THROTTLE_CLASSES'] = []

        self.settings_override = override_settings(
            STORMCLOUD_STORAGE_ROOT=self.test_storage_root,
            REST_FRAMEWORK=rest_framework_settings
        )
        self.settings_override.enable()

    def tearDown(self):
        """Clean up test-specific storage after each test."""
        super().tearDown()
        self.settings_override.disable()

        # Clean up user storage directory if it exists
        user_storage = self.test_storage_root / str(self.user.id)
        if user_storage.exists():
            shutil.rmtree(user_storage)

    def authenticate(self, user=None, api_key=None):
        """Authenticate requests with API key."""
        key = api_key or self.api_key
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {key.key}')

    def authenticate_session(self, user=None):
        """Authenticate requests with session."""
        user = user or self.user
        self.client.force_login(user)

    def create_admin(self):
        """Create and return an admin user with API key."""
        from accounts.tests.factories import UserWithProfileFactory, APIKeyFactory

        admin = UserWithProfileFactory(admin=True)
        key = APIKeyFactory(user=admin)
        return admin, key


class StormCloudAdminTestCase(StormCloudAPITestCase):
    """Base test case for admin endpoint tests."""

    def setUp(self):
        super().setUp()
        self.admin, self.admin_key = self.create_admin()
        self.authenticate(api_key=self.admin_key)
