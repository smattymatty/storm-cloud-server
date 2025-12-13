"""
Production settings for Storm Cloud Server.

Use this for Docker deployment and production environments.
"""

import os
from .base import *

# =============================================================================
# SENTRY ERROR TRACKING (OPTIONAL)
# =============================================================================
# Only initialize Sentry if SENTRY_DSN is provided in environment variables.
# This is completely optional - the app works fine without it.
# Free tier: https://sentry.io/signup/ (5K errors/month, 10K transactions/month)

SENTRY_DSN = config('SENTRY_DSN', default='')

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    import logging
    import re

    def filter_sensitive_data(event, hint):
        """
        Remove sensitive data from Sentry events before sending.
        Filters: API keys, passwords, tokens, file paths with user IDs.
        """
        # Filter request data
        if 'request' in event:
            if 'headers' in event['request']:
                # Redact Authorization header
                if 'Authorization' in event['request']['headers']:
                    event['request']['headers']['Authorization'] = '[Filtered]'

            # Redact form data with sensitive fields
            if 'data' in event['request']:
                sensitive_fields = ['password', 'api_key', 'token', 'secret', 'key']
                for field in sensitive_fields:
                    if field in event['request']['data']:
                        event['request']['data'][field] = '[Filtered]'

        # Filter exception messages containing API keys (looks like urlsafe base64)
        if 'exception' in event and 'values' in event['exception']:
            for exc in event['exception']['values']:
                if 'value' in exc:
                    # Redact anything that looks like a token (64 chars, urlsafe base64)
                    exc['value'] = re.sub(
                        r'[A-Za-z0-9_-]{64,}',
                        '[REDACTED_TOKEN]',
                        exc['value']
                    )

        return event

    sentry_sdk.init(
        dsn=SENTRY_DSN,

        # Integrations
        integrations=[
            DjangoIntegration(
                transaction_style='url',          # Use URL paths for transaction names
                middleware_spans=True,            # Track middleware performance
                signals_spans=False,              # Don't track signals (too noisy)
                cache_spans=True,                 # Track cache hit/miss
                http_methods_to_capture=(         # Only track these HTTP methods
                    "GET", "POST", "PUT", "PATCH", "DELETE"
                ),
            ),
            LoggingIntegration(
                level=logging.INFO,        # Capture info+ as breadcrumbs
                event_level=logging.ERROR  # Send errors+ as events
            ),
        ],

        # Performance Monitoring (optional, can be disabled by setting to 0.0)
        traces_sample_rate=config('SENTRY_TRACES_SAMPLE_RATE', default=0.1, cast=float),

        # Profiling (optional, requires traces_sample_rate > 0)
        profiles_sample_rate=config('SENTRY_PROFILES_SAMPLE_RATE', default=0.1, cast=float),

        # Environment & Release Tracking
        environment=config('ENVIRONMENT', default='production'),
        release=config('GIT_COMMIT', default='unknown'),

        # Privacy Settings
        send_default_pii=False,  # Don't send emails, IPs by default (GDPR-friendly)
        before_send=filter_sensitive_data,

        # Additional Options
        debug=False,  # Don't log Sentry debug info
        max_breadcrumbs=50,  # Limit breadcrumb trail
        attach_stacktrace=True,  # Always attach stack traces
    )

    # Log that Sentry is enabled (helpful for debugging)
    logger = logging.getLogger(__name__)
    logger.info(
        f"Sentry initialized for environment '{config('ENVIRONMENT', default='production')}'"
    )

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

# Production ALLOWED_HOSTS - must be explicitly set
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())

# Database configuration for production
# In Docker, use POSTGRES_* environment variables directly
# For VPS deployments, fall back to DATABASE_URL
if os.getenv('POSTGRES_HOST') and os.getenv('POSTGRES_HOST') != 'localhost':
    # Docker mode - construct PostgreSQL connection from environment variables
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('POSTGRES_DB', 'stormcloud'),
            'USER': os.getenv('POSTGRES_USER', 'stormcloud'),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD'),
            'HOST': os.getenv('POSTGRES_HOST'),
            'PORT': os.getenv('POSTGRES_PORT', '5432'),
            'CONN_MAX_AGE': 600,
        }
    }
# else: use DATABASES from base.py (which uses DATABASE_URL)

# WhiteNoise configuration for serving static files in production
# Insert after SecurityMiddleware but before all others
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Add WhiteNoise here
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# WhiteNoise static file settings
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# =============================================================================
# PRODUCTION SECURITY SETTINGS
# =============================================================================
# These settings enforce HTTPS, secure cookies, and security headers.
# Designed for deployment behind a reverse proxy (nginx/Caddy) with TLS.
# See SECURITY.md for detailed explanation and best practices.

# SSL/TLS Redirect - Default: False
# Let reverse proxy handle HTTP→HTTPS (recommended for Docker/nginx deployments)
# Set True only if Django should handle redirects directly (not common)
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)

# HTTP Strict Transport Security (HSTS) - Default: 31536000 (1 year)
# WARNING: Browsers will refuse HTTP connections for the specified duration.
# Start with 300 seconds (5 min) for testing, then increase to 31536000 (1 year).
# See: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True, cast=bool)
SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=True, cast=bool)

# Secure Cookies - Default: True
# Requires HTTPS. Cookies will only be sent over encrypted connections.
# Set False ONLY for local development HTTP testing (not recommended).
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=True, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=True, cast=bool)

# Additional Security Headers (always enabled in production)
SECURE_BROWSER_XSS_FILTER = True  # Enable browser XSS protection
SECURE_CONTENT_TYPE_NOSNIFF = True  # Prevent MIME type sniffing
X_FRAME_OPTIONS = 'DENY'  # Prevent clickjacking

# Logging configuration for production
# Docker deployments use console logging only (captured by docker logs)
# For traditional VPS deployments, add file handlers as needed
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': config('LOG_LEVEL', default='INFO'),
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': config('DJANGO_LOG_LEVEL', default='INFO'),
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

# Email configuration - must be set for production
EMAIL_BACKEND = config(
    'EMAIL_BACKEND',
    default='django.core.mail.backends.smtp.EmailBackend'
)

# Admin email for error notifications
ADMINS = [
    ('Storm Cloud Admin', config('ADMIN_EMAIL', default='admin@stormcloud.local')),
]
MANAGERS = ADMINS
