"""
Production settings for Storm Cloud Server.

Use this for Docker deployment and production environments.
"""

import os
from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config("DEBUG", default=False, cast=bool)

# Production ALLOWED_HOSTS - must be explicitly set
ALLOWED_HOSTS = config("ALLOWED_HOSTS", cast=Csv())

# Database configuration for production
# In Docker, use POSTGRES_* environment variables directly
# For VPS deployments, fall back to DATABASE_URL
if os.getenv("POSTGRES_HOST") and os.getenv("POSTGRES_HOST") != "localhost":
    # Docker mode - construct PostgreSQL connection from environment variables
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "stormcloud"),
            "USER": os.getenv("POSTGRES_USER", "stormcloud"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
            "HOST": os.getenv("POSTGRES_HOST"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 600,
        }
    }
# else: use DATABASES from base.py (which uses DATABASE_URL)

# WhiteNoise configuration for serving static files in production
# Insert after SecurityMiddleware but before all others
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # Add WhiteNoise here
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# WhiteNoise static file settings
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# =============================================================================
# PRODUCTION SECURITY SETTINGS
# =============================================================================
# These settings enforce HTTPS, secure cookies, and security headers.
# Designed for deployment behind a reverse proxy (nginx/Caddy) with TLS.
# See SECURITY.md for detailed explanation and best practices.

# SSL/TLS Redirect - Default: False
# Let reverse proxy handle HTTP→HTTPS (recommended for Docker/nginx deployments)
# Set True only if Django should handle redirects directly (not common)
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=False, cast=bool)

# HTTP Strict Transport Security (HSTS) - Default: 31536000 (1 year)
# WARNING: Browsers will refuse HTTP connections for the specified duration.
# Start with 300 seconds (5 min) for testing, then increase to 31536000 (1 year).
# See: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True, cast=bool
)
SECURE_HSTS_PRELOAD = config("SECURE_HSTS_PRELOAD", default=True, cast=bool)

# Secure Cookies - Default: True
# Requires HTTPS. Cookies will only be sent over encrypted connections.
# Set False ONLY for local development HTTP testing (not recommended).
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=True, cast=bool)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=True, cast=bool)


# Reuse CORS origins for CSRF (they're the same - frontend URLs)
CSRF_TRUSTED_ORIGINS = STORMCLOUD_CORS_ORIGINS

# Cross-subdomain cookie support (for split frontend/API domains)
_cookie_domain = config("STORMCLOUD_COOKIE_DOMAIN", default="")
if _cookie_domain:
    SESSION_COOKIE_DOMAIN = _cookie_domain
    CSRF_COOKIE_DOMAIN = _cookie_domain

# SameSite Cookie Policy
# 'Lax' is secure default for same-site requests (navigation + top-level GET)
# 'None' required for cross-site but less secure (requires Secure=True)
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# Additional Security Headers (always enabled in production)
SECURE_BROWSER_XSS_FILTER = True  # Enable browser XSS protection
SECURE_CONTENT_TYPE_NOSNIFF = True  # Prevent MIME type sniffing
X_FRAME_OPTIONS = "DENY"  # Prevent clickjacking

# Logging configuration for production
# Docker deployments use console logging only (captured by docker logs)
# For traditional VPS deployments, add file handlers as needed
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": config("LOG_LEVEL", default="INFO"),
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": config("DJANGO_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

# Email configuration - must be set for production
EMAIL_BACKEND = config(
    "EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"
)

# Admin email for error notifications
ADMINS = [
    ("Storm Cloud Admin", config("ADMIN_EMAIL", default="admin@stormcloud.local")),
]
MANAGERS = ADMINS

STORMCLOUD_FRONTEND_URL = config(
    "STORMCLOUD_FRONTEND_URL", default="https://stormdevelopments.ca"
)
