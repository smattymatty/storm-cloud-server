"""Middleware for adding context to Sentry error reports."""

try:
    from sentry_sdk import set_user, set_tag, set_context
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False


class SentryContextMiddleware:
    """
    Add user and request context to Sentry error reports.

    Only activates if Sentry SDK is installed and initialized.
    Safe to enable even if Sentry is not configured.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if SENTRY_AVAILABLE:
            # Add authenticated user info (privacy-safe)
            if hasattr(request, 'user') and request.user.is_authenticated:
                set_user({
                    "id": request.user.id,
                    "username": request.user.username,
                    "is_staff": request.user.is_staff,
                    # Explicitly NOT including: email, ip_address (GDPR)
                })

            # Add request context
            set_tag("request_path", request.path)
            set_tag("request_method", request.method)

            # Add custom context
            from django.conf import settings
            set_context("storage", {
                "backend": settings.STORMCLOUD_STORAGE_BACKEND,
            })

        return self.get_response(request)
