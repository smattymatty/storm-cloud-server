---
title: Monitoring & Error Tracking
published: 2025-12-11
modified: 2025-12-11
tags:
  - monitoring
  - sentry
  - production
  - observability
---

Storm Cloud Server supports optional error tracking and performance monitoring via [Sentry](https://sentry.io/).

---

## Overview

**Key Principle:** Monitoring is **completely optional**. Storm Cloud works perfectly fine without Sentry, using Django's built-in logging to `logs/security.log`.

### What Gets Tracked

**Without Sentry (Default):**
- Security events → `logs/security.log`
- Application errors → Django console logging
- Performance → None

**With Sentry (Optional):**
- Security events → `logs/security.log` (unchanged)
- Application errors → Sentry dashboard + Django logging
- Performance → Sentry tracing (10% sampling)
- User context → Attached to errors (user_id, username, is_staff)
- Privacy → API keys, passwords, tokens automatically filtered

---

## Setup Sentry (Optional)

### 1. Create Sentry Account

Visit [sentry.io/signup](https://sentry.io/signup/) and create a free account.

**Free tier includes:**
- 5,000 errors per month
- 10,000 performance transactions per month
- 30 day event retention
- Unlimited projects

### 2. Create Django Project

1. Click "Create Project"
2. Select **Django** as the platform
3. Set alert frequency (recommended: "Alert me on every new issue")
4. Name your project (e.g., "storm-cloud-production")
5. Click "Create Project"

### 3. Get Your DSN

After creating the project, Sentry will show you a DSN that looks like:

```
https://examplePublicKey@o0.ingest.sentry.io/0
```

Copy this DSN - you'll need it next.

### 4. Configure Environment

Add to your `.env` file:

```bash
# Sentry DSN (leave blank to disable)
SENTRY_DSN=https://examplePublicKey@o0.ingest.sentry.io/0

# Optional: Adjust sampling rates
SENTRY_TRACES_SAMPLE_RATE=0.1    # 10% of requests
SENTRY_PROFILES_SAMPLE_RATE=0.1  # 10% of traces

# Optional: Set environment name
ENVIRONMENT=production  # or staging, development
```

### 5. Install SDK & Restart

```bash
# If using Docker
docker compose down
docker compose up -d

# If using venv
pip install -r requirements.txt  # Installs sentry-sdk[django]
python manage.py runserver
```

Check logs for confirmation:
```
Sentry initialized for environment 'production'
```

---

## Testing Integration

### Debug Endpoint (Development Only)

Visit these endpoints to trigger test errors:

```bash
# Basic division error
curl http://localhost:8000/api/v1/debug/sentry-test/?type=division

# Value error
curl http://localhost:8000/api/v1/debug/sentry-test/?type=value

# API key filtering test
curl http://localhost:8000/api/v1/debug/sentry-test/?type=api_key
```

**Note:** This endpoint is **only available when `DEBUG=True`**. It will not exist in production.

### Verify in Sentry Dashboard

1. Go to your Sentry project
2. Click "Issues" in the left sidebar
3. You should see the test error appear within seconds
4. Click the error to see:
   - Stack trace
   - User context (if logged in)
   - Request details (URL, method)
   - Breadcrumbs (recent log messages)

---

## What's Tracked

### Errors

**Automatically captured:**
- All unhandled exceptions (500 errors)
- Python errors (ValueError, TypeError, etc.)
- Database errors
- Template rendering errors
- Middleware errors

**Example:**
```python
# This will be captured by Sentry
def my_view(request):
    user = User.objects.get(id=999)  # DoesNotExist error → Sentry
    return JsonResponse({"user": user.username})
```

### Performance

**Automatically tracked:**
- Endpoint response times
- Database query performance
- Cache hit/miss rates
- Middleware execution time

**Sampling:** Only 10% of requests are traced by default (configurable via `SENTRY_TRACES_SAMPLE_RATE`).

**Example transaction:**
```
POST /api/v1/files/document.pdf/upload/
├─ Middleware execution: 12ms
├─ Database query: 45ms
├─ File write: 230ms
└─ Total: 287ms
```

### User Context

When errors occur, Sentry automatically attaches:

```json
{
  "user": {
    "id": 42,
    "username": "alice",
    "is_staff": false
  },
  "tags": {
    "request_path": "/api/v1/files/test.txt/upload/",
    "request_method": "POST",
    "storage_backend": "local"
  }
}
```

**Privacy note:** Emails and IP addresses are **NOT** sent to Sentry by default (GDPR-compliant).

---

## Privacy & Security

### What's Filtered

Storm Cloud **automatically redacts** sensitive data before sending to Sentry:

1. **Authorization headers** - `Bearer xxx` → `[Filtered]`
2. **Password fields** - Any form field named `password`, `api_key`, `token`, `secret`, `key`
3. **API keys in error messages** - 64+ character tokens → `[REDACTED_TOKEN]`

**Example:**

```python
# Before filtering
raise Exception("Failed to authenticate with key: abc123xyz...")

# Sent to Sentry
raise Exception("Failed to authenticate with key: [REDACTED_TOKEN]")
```

### GDPR Compliance

Sentry integration is configured to be GDPR-compliant:

- `send_default_pii=False` - No emails or IP addresses
- User context limited to: `id`, `username`, `is_staff`
- No tracking cookies or client-side monitoring
- Data retention: 30 days (Sentry free tier)

### Opting Out

Users cannot opt out individually (server-side errors). To disable Sentry entirely:

1. Remove `SENTRY_DSN` from `.env`
2. Restart application
3. Errors will only be logged to Django console/files

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SENTRY_DSN` | `""` | Sentry Data Source Name. Leave blank to disable. |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.1` | Percentage of requests to trace (0.0 to 1.0). `0.1` = 10%. |
| `SENTRY_PROFILES_SAMPLE_RATE` | `0.1` | Percentage of traces to profile (0.0 to 1.0). Requires traces > 0. |
| `ENVIRONMENT` | `production` | Environment name shown in Sentry (production, staging, dev). |
| `GIT_COMMIT` | `unknown` | Git commit hash for release tracking. Auto-set by CI/CD. |

### Example Configurations

**Production (recommended):**
```bash
SENTRY_DSN=https://xxx@xxx.ingest.sentry.io/xxx
SENTRY_TRACES_SAMPLE_RATE=0.1   # 10% sampling
SENTRY_PROFILES_SAMPLE_RATE=0.1
ENVIRONMENT=production
```

**Staging (higher sampling):**
```bash
SENTRY_DSN=https://xxx@xxx.ingest.sentry.io/xxx
SENTRY_TRACES_SAMPLE_RATE=0.5   # 50% sampling
SENTRY_PROFILES_SAMPLE_RATE=0.5
ENVIRONMENT=staging
```

**Development (disabled):**
```bash
SENTRY_DSN=  # Leave blank
```

---

## Operational Guide

### Responding to Sentry Alerts

When you receive a Sentry alert:

1. **Check severity** - Is this affecting multiple users or just one?
2. **Review context** - What user, endpoint, and action triggered it?
3. **Check recent deployments** - Did this start after a recent release?
4. **Reproduce** - Can you trigger the error yourself?
5. **Fix and deploy** - Resolve the issue and push a fix
6. **Verify** - Mark the issue as "Resolved" in Sentry

### Common False Positives

**404 errors for share links:**
- Expected when share link expires or is invalid
- Mark as "Ignore" in Sentry

**Rate limiting errors:**
- Expected when users exceed throttle limits
- Already handled gracefully by API
- Mark as "Ignore" in Sentry

**Database connection during restart:**
- Expected during deployments
- Temporary and self-healing
- Mark as "Ignore" in Sentry

### Best Practices

1. **Set up alerts** - Configure Slack/email notifications in Sentry
2. **Use releases** - Tag deployments with git commit hash (`GIT_COMMIT`)
3. **Create teams** - Invite team members to Sentry project
4. **Monitor trends** - Check Sentry dashboard weekly for patterns
5. **Clean up** - Archive or ignore resolved/wontfix issues monthly

---

## Performance Monitoring

### Understanding Transactions

Transactions represent complete request/response cycles:

```
GET /api/v1/files/document.pdf/download/
Duration: 523ms
├─ middleware.security          12ms
├─ middleware.cors              3ms
├─ middleware.sentry_context    2ms
├─ middleware.session           8ms
├─ authentication               15ms
├─ view.file_download           480ms
│  ├─ database.query            25ms
│  ├─ filesystem.read           450ms
│  └─ response.prepare          5ms
└─ middleware.total             523ms
```

### Slow Query Detection

Sentry automatically highlights slow database queries:

```
SELECT * FROM storage_storedfile WHERE owner_id = 1 AND path LIKE '%test%'
Duration: 450ms (SLOW)
```

**Solution:** Add database index or optimize query.

### Cache Performance

Monitor cache hit/miss rates:

```
cache.get('user_profile_42')
Result: HIT (2ms)

cache.get('user_profile_43')
Result: MISS (0ms) → database query (25ms)
```

---

## Troubleshooting

### Sentry Not Capturing Errors

**Problem:** Errors occur but don't appear in Sentry.

**Solutions:**

1. **Verify DSN is set:**
   ```bash
   docker compose exec web env | grep SENTRY_DSN
   ```

2. **Check initialization:**
   ```bash
   docker compose logs web | grep "Sentry initialized"
   ```

3. **Test with debug endpoint:**
   ```bash
   curl http://localhost:8000/api/v1/debug/sentry-test/?type=division
   ```

4. **Check Sentry quota:**
   - Go to Sentry → Settings → Quota Management
   - Ensure you haven't exceeded 5K errors/month

### Errors Sent But Privacy Data Leaked

**Problem:** API keys or passwords appearing in Sentry.

**Solution:** This shouldn't happen, but if it does:

1. **Delete the event** in Sentry dashboard
2. **Report the issue** on GitHub
3. **Verify `before_send` filter** in `_core/settings/production.py`

### Too Many Errors

**Problem:** Sentry quota exceeded due to error spam.

**Solutions:**

1. **Increase sample rate filtering:**
   ```bash
   SENTRY_TRACES_SAMPLE_RATE=0.01  # 1% instead of 10%
   ```

2. **Ignore specific errors:**
   - Go to Sentry → Settings → Inbound Filters
   - Add error patterns to ignore

3. **Fix the root cause** (obviously!)

---

## Disabling Sentry

To disable Sentry entirely:

### Option 1: Remove DSN (Recommended)

Edit `.env`:
```bash
SENTRY_DSN=  # Leave blank or comment out
```

Restart:
```bash
docker compose restart web
```

### Option 2: Uninstall SDK

Edit `requirements.txt` and remove:
```
sentry-sdk[django]>=2.0.0
```

Rebuild:
```bash
docker compose build web
docker compose up -d
```

---

## Advanced Topics

### Custom Error Tags

Add custom tags in your code:

```python
from sentry_sdk import set_tag

def my_view(request):
    set_tag("payment_provider", "stripe")
    set_tag("user_tier", "premium")
    # Your code here
```

### Manual Error Capture

Capture errors without raising:

```python
from sentry_sdk import capture_exception

try:
    risky_operation()
except Exception as e:
    capture_exception(e)
    # Continue execution
```

### Performance Measurements

Track custom operations:

```python
from sentry_sdk import start_transaction

with start_transaction(op="task", name="video_encoding"):
    encode_video(video_file)
```

---

## Related Documentation

- [Security Guide](../SECURITY.md) - Security best practices
- [Setup Guide](setup.md) - Installation instructions
- [Architecture Decisions](../architecture/records/) - Design rationale

---

## Getting Help

**Sentry Issues:**
- [Sentry Documentation](https://docs.sentry.io/)
- [Sentry Discord](https://discord.gg/sentry)

**Storm Cloud Issues:**
- [GitHub Issues](https://github.com/smattymatty/storm-cloud-server/issues)
- Tag with `monitoring` label
