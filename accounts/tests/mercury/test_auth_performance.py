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
