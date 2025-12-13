---
name: Add Optional Sentry Error Tracking
about: Integrate Sentry for production error monitoring (optional, opt-in)
title: 'Add optional Sentry error tracking and performance monitoring'
labels: 'enhancement, monitoring, production'
assignees: ''
---

# Add Optional Sentry Error Tracking & Performance Monitoring

## Overview
Storm Cloud already has **excellent security event logging** to `logs/security.log` via the `stormcloud.security` logger. This issue adds **optional application error tracking** to catch exceptions, performance issues, and user-facing errors in production.

**Key principle:** Sentry is **opt-in only** - if `SENTRY_DSN` is not set, the app runs normally with existing logging.

## What We Already Have ✅
- ✅ Security event logging ([accounts/signal_handlers.py:17](../../accounts/signal_handlers.py#L17))
- ✅ File-based logging to `logs/security.log` (tracks auth events, API key ops)
- ✅ Structured logging with user_id, IP addresses, event types
- ✅ Django signals for security events (login, registration, API key operations)
- ✅ Production logging config in [_core/settings/production.py:85-116](../../_core/settings/production.py#L85-L116)
- ✅ `ADMINS` configured for error emails ([_core/settings/production.py:125-128](../../_core/settings/production.py#L125-L128))

## What This Adds 🆕
- ⭐ **Real-time error tracking** (exceptions, 500 errors, crashes)
- ⭐ **Performance monitoring** (slow endpoints, database queries, cache hits/misses)
- ⭐ **Error alerting** (Slack/email notifications for critical issues)
- ⭐ **User context in errors** (which user hit the bug?)
- ⭐ **Release tracking** (what version introduced the bug?)
- ⭐ **Error grouping & deduplication** (avoid spam)

## Logging Architecture After This Change

```
┌─────────────────────────────────────┐
│         Storm Cloud Server          │
├─────────────────────────────────────┤
│                                     │
│  Security Events                    │
│  (auth, API keys, access)          │
│         │                           │
│         ├──► logs/security.log      │ ← Existing
│         └──► Django logging         │
│                                     │
│  Application Errors                 │
│  (500s, exceptions, crashes)       │
│         │                           │
│         ├──► Django logging         │ ← Existing
│         └──► Sentry.io (optional)   │ ← New (if SENTRY_DSN set)
│                                     │
│  Performance Data                   │
│  (slow queries, endpoints)         │
│         │                           │
│         └──► Sentry Tracing         │ ← New (if SENTRY_DSN set)
│              (optional)             │
│                                     │
└─────────────────────────────────────┘
```

---

## Implementation Tasks

### 1. Install Sentry SDK
- [ ] Add `sentry-sdk[django]>=2.0.0` to [requirements.txt](../../requirements.txt)
- [ ] Update requirements in development environment
- [ ] Update [Dockerfile](../../Dockerfile) (pip install will pick it up automatically)

### 2. Configure Optional Sentry in Production Settings
- [ ] Add Sentry initialization to [_core/settings/production.py](../../_core/settings/production.py) (after imports, before LOGGING)
- [ ] **Crucial:** Only initialize if `SENTRY_DSN` is provided (opt-in)
- [ ] Configure Django integration with sensible defaults
- [ ] Set up privacy-respecting defaults (`send_default_pii=False`)
- [ ] Add custom `before_send` filter for sensitive data

**Implementation:**

Add to `_core/settings/production.py` after line 8 (`from .base import *`):

```python
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

        # Filter exception messages containing API keys (starts with urlsafe base64)
        if 'exception' in event and 'values' in event['exception']:
            for exc in event['exception']['values']:
                if 'value' in exc:
                    # Redact anything that looks like a token (64 chars, urlsafe base64)
                    import re
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
    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        f"Sentry initialized for environment '{config('ENVIRONMENT', default='production')}'"
    )
```

### 3. Add User Context Middleware (Optional Enhancement)
- [ ] Create `core/middleware.py` for Sentry context
- [ ] Add authenticated user info to error reports (user_id, username, is_staff)
- [ ] Add custom tags: `storage_backend`, `request_path`
- [ ] Register middleware in `MIDDLEWARE` setting

**Implementation:**

Create `core/middleware.py`:

```python
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
```

Add to `_core/settings/base.py` MIDDLEWARE (after CorsMiddleware):

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'core.middleware.SentryContextMiddleware',  # Add this line
    'django.contrib.sessions.middleware.SessionMiddleware',
    # ... rest of middleware
]
```

### 4. Update Environment Configuration
- [ ] Add Sentry variables to [.env.template](../../.env.template)
- [ ] Document Sentry free tier and signup link
- [ ] Explain each configuration option

**Add to `.env.template`** (after EMAIL configuration):

```bash
# ===============================================================================
# SENTRY ERROR TRACKING (OPTIONAL)
# ===============================================================================
# Sentry provides real-time error tracking and performance monitoring.
# This is OPTIONAL - leave SENTRY_DSN blank to disable.
#
# Free tier: https://sentry.io/signup/
# - 5,000 errors per month
# - 10,000 performance transactions per month
# - 30 day event retention
#
# To enable:
# 1. Create free Sentry account at https://sentry.io/signup/
# 2. Create a new Python/Django project
# 3. Copy your DSN from Project Settings > Client Keys (DSN)
# 4. Paste DSN below and restart your application

# Sentry DSN (leave blank to disable error tracking)
SENTRY_DSN=

# Percentage of requests to track for performance (0.0 to 1.0)
# 0.1 = 10% of requests (recommended for production)
# Set to 0.0 to disable performance monitoring
SENTRY_TRACES_SAMPLE_RATE=0.1

# Percentage of traces to profile (0.0 to 1.0)
# 0.1 = 10% of traces (recommended for production)
# Requires traces_sample_rate > 0
SENTRY_PROFILES_SAMPLE_RATE=0.1

# Environment name (shown in Sentry dashboard)
ENVIRONMENT=production

# Git commit hash for release tracking (optional)
# Auto-set by CI/CD or docker build
# GIT_COMMIT=
```

### 5. Add Debug Endpoint for Testing (Development Only)
- [ ] Create test endpoint in `api/v1/urls.py` (only if DEBUG=True)
- [ ] Add view that deliberately raises different error types
- [ ] Test error appears in Sentry dashboard
- [ ] Verify user context is attached
- [ ] Verify sensitive data is filtered

**Implementation:**

Add to `api/v1/urls.py`:

```python
from django.conf import settings

# Development-only Sentry test endpoint
if settings.DEBUG:
    from django.http import JsonResponse

    def sentry_test_error(request):
        """
        Test endpoint for Sentry integration.
        Raises deliberate errors to verify Sentry is working.

        Only available when DEBUG=True.
        """
        error_type = request.GET.get('type', 'division')

        if error_type == 'division':
            # Test basic exception
            return 1 / 0
        elif error_type == 'value':
            # Test value error
            raise ValueError("Test error from Storm Cloud - this is intentional!")
        elif error_type == 'api_key':
            # Test sensitive data filtering
            fake_key = "test_api_key_1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_-"
            raise Exception(f"Error with API key: {fake_key}")
        else:
            return JsonResponse({
                "message": "Sentry test endpoint",
                "usage": "Add ?type=division, ?type=value, or ?type=api_key to trigger errors"
            })

    urlpatterns += [
        path('debug/sentry-test/', sentry_test_error, name='sentry-test'),
    ]
```

### 6. Update Documentation
- [ ] Update [README.md](../../README.md) with monitoring section
- [ ] Update [DOCKER.md](../../DOCKER.md) with Sentry setup steps
- [ ] Create `docs/MONITORING.md` with operational guide
- [ ] Document how to respond to Sentry alerts

**Add to `README.md`** (after "Testing" section):

```markdown
## Monitoring (Optional)

Storm Cloud supports optional error tracking and performance monitoring via [Sentry](https://sentry.io/).

### Enable Sentry

1. Create free Sentry account: https://sentry.io/signup/
2. Create new Python/Django project
3. Copy your DSN from Project Settings
4. Add to `.env`:
   ```bash
   SENTRY_DSN=https://xxx@xxx.ingest.sentry.io/xxx
   ```
5. Restart application

### Test Integration (Development)

Visit `http://127.0.0.1:8000/api/v1/debug/sentry-test/?type=division` to trigger a test error.

### What's Tracked

- **Errors**: Unhandled exceptions, 500 errors, crashes
- **Performance**: Slow endpoints, database queries, cache hits/misses
- **Context**: User info, request path, storage backend
- **Privacy**: API keys, passwords, and tokens are automatically filtered

See [docs/MONITORING.md](docs/MONITORING.md) for operational guide.
```

---

## Testing Checklist

### Local Testing
- [ ] Install `sentry-sdk[django]` in virtual environment
- [ ] Leave `SENTRY_DSN` blank - app should run normally
- [ ] Set `SENTRY_DSN` to test value - app should initialize Sentry
- [ ] Trigger test error via `/api/v1/debug/sentry-test/`
- [ ] Verify error appears in Sentry dashboard
- [ ] Check user context is attached (user_id, username, is_staff)
- [ ] Verify API key filtering works (`?type=api_key`)
- [ ] Remove `SENTRY_DSN` - app should run without errors

### Production Testing
- [ ] Deploy with `SENTRY_DSN` set
- [ ] Trigger test error in staging environment
- [ ] Verify error grouping (multiple identical errors = 1 group)
- [ ] Test performance transaction capture (file upload should create span)
- [ ] Verify release tracking (git commit shown in Sentry)
- [ ] Test alert notifications (Slack/email)

---

## Acceptance Criteria

- [ ] Sentry SDK installed in [requirements.txt](../../requirements.txt)
- [ ] Sentry initialization is **opt-in** (only if `SENTRY_DSN` set)
- [ ] Application runs normally without Sentry (backward compatible)
- [ ] Environment variables documented in [.env.template](../../.env.template)
- [ ] Sensitive data filtered (API keys, passwords, tokens)
- [ ] User context attached to errors (user_id, username, is_staff)
- [ ] Performance monitoring captures database queries and cache operations
- [ ] Test endpoint available in DEBUG mode
- [ ] Documentation updated ([README.md](../../README.md), [DOCKER.md](../../DOCKER.md))
- [ ] No breaking changes to existing logging infrastructure

---

## Priority
**HIGH** - Critical for production deployments. Without error tracking, you'll only learn about bugs when users complain (if they report them at all).

## Estimated Effort
**4-6 hours**
- 1 hour: Sentry SDK installation + configuration
- 1 hour: Privacy filtering implementation
- 1 hour: Middleware for user context
- 1 hour: Testing + validation
- 1 hour: Documentation updates

## Dependencies
- Sentry account (free tier: https://sentry.io/signup/)
- Optional: Team organization for collaboration

## References
- [Sentry Django Integration Docs](https://docs.sentry.io/platforms/python/integrations/django/)
- [Sentry Performance Monitoring](https://docs.sentry.io/product/performance/)
- [Sentry Data Privacy](https://docs.sentry.io/platforms/python/data-management/sensitive-data/)
- Existing security logging: [accounts/signal_handlers.py](../../accounts/signal_handlers.py)

---

## Non-Goals

This issue does **NOT** include:
- ❌ Replacing existing security logging (security.log stays)
- ❌ Making Sentry mandatory
- ❌ Sending user emails or IP addresses to Sentry (GDPR-compliant)
- ❌ Frontend error tracking (backend only)
- ❌ Custom Sentry integrations (use Django's built-in integration)
