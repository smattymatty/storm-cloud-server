"""Performance tests for authentication endpoints using Django Mercury."""

from rest_framework.test import APITestCase
from django_mercury import monitor
from accounts.tests.factories import UserWithProfileFactory, APIKeyFactory


class AuthEndpointPerformance(APITestCase):
    """Performance baselines for auth endpoints."""

    def setUp(self):
        super().setUp()
        self.user = UserWithProfileFactory(verified=True)
        self.user.set_password('testpass123')
        self.user.save()
        self.api_key = APIKeyFactory(user=self.user)

    def test_login_under_800ms(self):
        """Login should complete under 800ms."""
        with monitor(response_time_ms=800, query_count=11) as result:
            response = self.client.post('/api/v1/auth/login/', {
                'username': self.user.username,
                'password': 'testpass123'
            })

        self.assertEqual(response.status_code, 200)

    def test_auth_me_under_50ms(self):
        """Auth me should complete under 50ms."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.api_key.key}')

        with monitor(response_time_ms=50) as result:
            response = self.client.get('/api/v1/auth/me/')
        result.explain()

        self.assertEqual(response.status_code, 200)

    def test_token_create_under_100ms(self):
        """Token generation should complete under 100ms."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.api_key.key}')

        with monitor(response_time_ms=100) as result:
            response = self.client.post('/api/v1/auth/tokens/', {
                'name': 'perf-test-key'
            })

        self.assertEqual(response.status_code, 201)


class TokenListPerformance(APITestCase):
    """Test token listing at scale."""

    def setUp(self):
        super().setUp()
        self.user = UserWithProfileFactory(verified=True)
        # Create 50 tokens to test at scale
        for i in range(50):
            APIKeyFactory(user=self.user, name=f'key-{i}')
        self.auth_key = APIKeyFactory(user=self.user, name='auth-key')

    def test_list_50_tokens_under_50ms_no_n1(self):
        """Listing 50 tokens should be fast with no N+1."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.auth_key.key}')

        with monitor(response_time_ms=50, query_count=5) as result:
            response = self.client.get('/api/v1/auth/tokens/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total'], 51)  # 50 + auth_key


class AdminUserEndpointPerformance(APITestCase):
    """Performance baselines for admin user management endpoints."""

    def setUp(self):
        super().setUp()
        self.admin = UserWithProfileFactory(is_staff=True, is_superuser=True, verified=True)
        self.admin_key = APIKeyFactory(user=self.admin)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.admin_key.key}')

    def test_admin_user_list_under_200ms(self):
        """Admin user list should complete under 200ms with 50 users."""
        # Create 50 users to test at scale
        from django.contrib.auth import get_user_model
        User = get_user_model()
        existing_count = User.objects.count()

        for i in range(50):
            UserWithProfileFactory()

        with monitor(response_time_ms=200) as result:
            response = self.client.get('/api/v1/admin/users/')

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data['total'], existing_count + 50)

    def test_admin_user_detail_under_100ms(self):
        """Admin user detail should complete under 100ms."""
        user = UserWithProfileFactory()
        # Create some API keys for the user
        for i in range(5):
            APIKeyFactory(user=user, name=f'key-{i}')

        with monitor(response_time_ms=100) as result:
            response = self.client.get(f'/api/v1/admin/users/{user.id}/')

        self.assertEqual(response.status_code, 200)
        self.assertIn('user', response.data)
        self.assertIn('api_keys', response.data)

    def test_admin_user_update_under_100ms(self):
        """Admin user update should complete under 100ms."""
        user = UserWithProfileFactory()

        with monitor(response_time_ms=100) as result:
            response = self.client.patch(
                f'/api/v1/admin/users/{user.id}/',
                {'email': 'updated@example.com'},
                format='json'
            )

        self.assertEqual(response.status_code, 200)

    def test_admin_user_delete_under_100ms(self):
        """Admin user deletion should complete under 100ms."""
        user = UserWithProfileFactory()
        # Create related objects to test cascade deletion
        for i in range(10):
            APIKeyFactory(user=user, name=f'key-{i}')

        # Allow up to 12 queries for deletion (cascades to profile, API keys, etc.)
        with monitor(response_time_ms=100, query_count=12) as result:
            response = self.client.delete(f'/api/v1/admin/users/{user.id}/')

        self.assertEqual(response.status_code, 200)

    def test_admin_password_reset_under_1000ms(self):
        """Admin password reset should complete under 1s (password hashing is slow)."""
        user = UserWithProfileFactory()

        # Password hashing is intentionally slow for security
        with monitor(response_time_ms=1000) as result:
            response = self.client.post(
                f'/api/v1/admin/users/{user.id}/reset-password/',
                {'new_password': 'newpass123'},
                format='json'
            )

        self.assertEqual(response.status_code, 200)
