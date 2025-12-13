"""Custom throttle classes for Storm Cloud Server.

See ADR 007: Rate Limiting Strategy for design rationale.
"""

from rest_framework.throttling import UserRateThrottle, AnonRateThrottle


class LoginRateThrottle(UserRateThrottle):
    """
    Throttle for login attempts.

    Rate: 5 requests per minute (default)
    Scope: 'login'

    Applied to: /api/v1/auth/login/
    Purpose: Prevent brute force password attacks
    """
    scope = 'login'


class AuthRateThrottle(UserRateThrottle):
    """
    Throttle for authentication-related operations.

    Rate: 10 requests per hour (default)
    Scope: 'auth'

    Applied to:
    - /api/v1/auth/register/
    - /api/v1/auth/tokens/ (POST - create API key)

    Purpose: Prevent spam registration and API key farming
    """
    scope = 'auth'


class UploadRateThrottle(UserRateThrottle):
    """
    Throttle for file uploads.

    Rate: 100 requests per hour (default)
    Scope: 'uploads'

    Applied to: /api/v1/files/*/upload/
    Purpose: Manage bandwidth and storage resources
    """
    scope = 'uploads'


class DownloadRateThrottle(UserRateThrottle):
    """
    Throttle for file downloads.

    Rate: 500 requests per hour (default)
    Scope: 'downloads'

    Applied to: /api/v1/files/*/download/
    Purpose: Manage bandwidth, higher than upload for read-heavy workloads
    """
    scope = 'downloads'


class AnonLoginThrottle(AnonRateThrottle):
    """
    Throttle for anonymous login attempts (IP-based).

    Rate: 10 requests per hour (default)
    Scope: 'anon_login'

    Applied to: /api/v1/auth/login/ for unauthenticated requests
    Purpose: Additional IP-based protection against distributed brute force
    """
    scope = 'anon_login'


class AnonRegistrationThrottle(AnonRateThrottle):
    """
    Throttle for anonymous registration attempts (IP-based).

    Rate: 5 requests per hour (default)
    Scope: 'anon_registration'

    Applied to: /api/v1/auth/register/ for unauthenticated requests
    Purpose: Prevent spam account creation from single IP
    """
    scope = 'anon_registration'


class PublicShareRateThrottle(AnonRateThrottle):
    """
    Throttle for public share link access (IP-based).

    Rate: 60 requests per minute (default)
    Scope: 'public_share'

    Applied to: /api/v1/public/{token}/ endpoints
    Purpose: Prevent abuse of public share links
    """
    scope = 'public_share'


class PublicShareDownloadRateThrottle(AnonRateThrottle):
    """
    Throttle for public share file downloads (IP-based).

    Rate: 30 requests per minute (default)
    Scope: 'public_share_download'

    Applied to: /api/v1/public/{token}/download/ endpoint
    Purpose: Prevent bandwidth abuse via downloads
    """
    scope = 'public_share_download'
