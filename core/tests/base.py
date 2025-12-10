"""Base test classes for Storm Cloud API tests."""

from rest_framework.test import APITestCase


class StormCloudAPITestCase(APITestCase):
    """Base test case with common setup for Storm Cloud tests."""

    def setUp(self):
        super().setUp()
        # Import here to avoid circular imports
        from accounts.tests.factories import UserWithProfileFactory, APIKeyFactory

        self.user = UserWithProfileFactory(verified=True)
        self.api_key = APIKeyFactory(user=self.user)

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
