# Security Guide

Production security configuration for Storm Cloud Server.

## Table of Contents

- [Overview](#overview)
- [Security Settings Explained](#security-settings-explained)
- [Deployment Checklist](#deployment-checklist)
- [Common Scenarios](#common-scenarios)
- [Troubleshooting](#troubleshooting)

---

## Overview

Storm Cloud Server is designed to run behind a **reverse proxy** (nginx, Caddy, Traefik) that handles TLS/SSL termination. The application layer enforces additional security through Django's security middleware.

### Security Architecture

```
Internet → Reverse Proxy (HTTPS) → Storm Cloud (HTTP on 8000)
           ├─ TLS/SSL termination
           ├─ HTTP→HTTPS redirect
           └─ Security headers
```

**Key Principle:** The reverse proxy handles encryption and redirects. Django enforces secure cookies and HSTS.

---

## Security Settings Explained

### 1. SECURE_SSL_REDIRECT

**What it does:** Redirects all HTTP requests to HTTPS at the Django level.

**Recommended value:** `False`

**Why:** Your reverse proxy (nginx/Caddy) should handle HTTP→HTTPS redirects. This is more efficient and works correctly with load balancers and health checks.

**Set to `True` ONLY if:**
- Running Django directly on the internet (not recommended)
- No reverse proxy in front of Django

**Example nginx config (recommended approach):**
```nginx
server {
    listen 80;
    server_name cloud.example.com;
    return 301 https://$server_name$request_uri;
}
```

---

### 2. SECURE_HSTS_SECONDS

**What it does:** Tells browsers to ONLY use HTTPS for your domain for the specified duration.

**Recommended value:** Start with `300` (5 minutes), increase to `31536000` (1 year) after testing.

**⚠️ WARNING:** This setting has **irreversible consequences** during the HSTS period:
- If you disable HTTPS, browsers will refuse to connect
- If your SSL certificate expires, users cannot access your site
- Cannot be undone without waiting for the duration to expire

**Rollout Strategy:**
1. Start with 300 seconds (5 minutes)
2. Test thoroughly for 24-48 hours
3. Increase to 86400 (1 day)
4. Test for 1 week
5. Increase to 31536000 (1 year) for production

**Set to `0` to disable HSTS** (not recommended for production).

**Related settings:**
- `SECURE_HSTS_INCLUDE_SUBDOMAINS=True` - Applies HSTS to all subdomains
- `SECURE_HSTS_PRELOAD=True` - Allows inclusion in browser HSTS preload lists

**Resources:**
- [MDN: Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security)
- [hstspreload.org](https://hstspreload.org/)

---

### 3. SESSION_COOKIE_SECURE

**What it does:** Ensures session cookies are only sent over HTTPS.

**Recommended value:** `True`

**Why:** Prevents session hijacking over unencrypted connections.

**⚠️ IMPORTANT:** Your site **will not work** without HTTPS if this is enabled. Session authentication will fail on HTTP.

**Set to `False` ONLY for:**
- Local development on `http://localhost`
- Testing without SSL (NOT production)

---

### 4. CSRF_COOKIE_SECURE

**What it does:** Ensures CSRF protection cookies are only sent over HTTPS.

**Recommended value:** `True`

**Why:** Prevents CSRF token theft over unencrypted connections.

**Same caveats as SESSION_COOKIE_SECURE** - requires HTTPS to function.

---

### 5. Additional Security Headers (Always Enabled)

These are automatically configured in `production.py`:

| Header | Value | Purpose |
|--------|-------|---------|
| `X-Content-Type-Options` | `nosniff` | Prevents MIME type confusion attacks |
| `X-Frame-Options` | `DENY` | Prevents clickjacking attacks |
| `X-XSS-Protection` | `1; mode=block` | Enables browser XSS filtering |

---

## Deployment Checklist

Use this checklist before exposing Storm Cloud to the internet:

### Pre-Deployment

- [ ] SECRET_KEY is set to a unique, random value (not the default)
- [ ] POSTGRES_PASSWORD is set to a strong password
- [ ] DEBUG is set to `False` in `.env`
- [ ] ALLOWED_HOSTS includes your domain (e.g., `cloud.example.com`)

### Reverse Proxy Setup

- [ ] HTTPS/TLS is configured (Let's Encrypt, commercial cert, etc.)
- [ ] HTTP→HTTPS redirect is enabled at proxy level
- [ ] Proxy passes `X-Forwarded-Proto` header to Django
- [ ] Health check endpoint `/api/v1/health/ping/` is accessible

### Security Settings

- [ ] SECURE_HSTS_SECONDS is set (start with 300, increase gradually)
- [ ] SESSION_COOKIE_SECURE is `True` (default)
- [ ] CSRF_COOKIE_SECURE is `True` (default)
- [ ] SECURE_SSL_REDIRECT is `False` (proxy handles redirects)

### Infrastructure

- [ ] Firewall allows only ports 80/443 (block 8000 from internet)
- [ ] PostgreSQL is not exposed to internet (Docker internal network)
- [ ] Regular backups configured (`make backup`)
- [ ] Log monitoring in place (`docker compose logs`)

### Validation

- [ ] Run `python manage.py check --deploy` (with production settings)
- [ ] Test login over HTTPS
- [ ] Verify session cookies have `Secure` flag (browser DevTools)
- [ ] Check security headers with [securityheaders.com](https://securityheaders.com/)

---

## Common Scenarios

### Scenario 1: Docker + nginx/Caddy (Recommended)

**Setup:**
- Docker runs Storm Cloud on internal network
- nginx/Caddy handles HTTPS and forwards to Docker

**.env configuration:**
```bash
DEBUG=False
ALLOWED_HOSTS=cloud.example.com
SECURE_SSL_REDIRECT=False  # nginx handles redirects
SECURE_HSTS_SECONDS=31536000  # After testing period
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

**nginx config:**
```nginx
server {
    listen 443 ssl http2;
    server_name cloud.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

### Scenario 2: VPS with Cloudflare

**Setup:**
- Cloudflare provides SSL (Full or Full Strict mode)
- Origin traffic can be HTTP or HTTPS

**.env configuration:**
```bash
DEBUG=False
ALLOWED_HOSTS=cloud.example.com
SECURE_SSL_REDIRECT=False  # Cloudflare handles redirects
SECURE_HSTS_SECONDS=31536000
SESSION_COOKIE_SECURE=True  # Cloudflare presents HTTPS to browsers
CSRF_COOKIE_SECURE=True
```

**Cloudflare SSL Mode:** Use "Full (strict)" for maximum security.

---

### Scenario 3: Development/Staging without HTTPS

**⚠️ NOT for production** - For testing environments only.

**.env configuration:**
```bash
DEBUG=True
ALLOWED_HOSTS=*
SECURE_SSL_REDIRECT=False
SECURE_HSTS_SECONDS=0  # Disable HSTS
SESSION_COOKIE_SECURE=False  # Allow HTTP cookies
CSRF_COOKIE_SECURE=False  # Allow HTTP CSRF
```

---

## Troubleshooting

### Problem: "Unable to connect" after enabling HSTS

**Cause:** Browser has cached HSTS header and refuses HTTP connections.

**Solution:**
1. Enable HTTPS on your server
2. Or, wait for HSTS expiry (as configured in SECURE_HSTS_SECONDS)
3. Or, clear browser HSTS settings:
   - Chrome: `chrome://net-internals/#hsts` → Delete domain
   - Firefox: Delete `SiteSecurityServiceState.txt` in profile folder
   - Safari: No easy way - wait for expiry

**Prevention:** Always start with a low HSTS value (300 seconds) during testing.

---

### Problem: Session authentication doesn't work

**Symptom:** Login succeeds but `/api/v1/auth/me/` returns 401 Unauthorized.

**Cause:** SESSION_COOKIE_SECURE is `True` but site is accessed over HTTP.

**Solution:**
1. Enable HTTPS (required for production)
2. Or, for local testing only: Set `SESSION_COOKIE_SECURE=False` in `.env`

---

### Problem: CSRF validation failed

**Symptom:** POST requests return 403 Forbidden with CSRF error.

**Cause:** CSRF_COOKIE_SECURE is `True` but site is accessed over HTTP.

**Solution:**
1. Enable HTTPS (required for production)
2. Or, for local testing only: Set `CSRF_COOKIE_SECURE=False` in `.env`
3. Ensure your client includes CSRF token in requests (API key auth bypasses CSRF)

---

### Problem: Django check warnings on security settings

**Symptom:** Running `python manage.py check --deploy` shows security warnings.

**Cause:** You're running the check with dev settings (DEBUG=True) or environment variables aren't set.

**Solution:**
1. Run with production settings: `DJANGO_SETTINGS_MODULE=_core.settings.production python manage.py check --deploy`
2. Or, verify your `.env` file has production values:
   - `DEBUG=False`
   - `SECURE_HSTS_SECONDS=31536000`
   - `SESSION_COOKIE_SECURE=True`
   - `CSRF_COOKIE_SECURE=True`

**Note:** The warnings are informational - production settings already have correct defaults.

---

## Additional Resources

- [Django Security Checklist](https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/)
- [OWASP Secure Headers Project](https://owasp.org/www-project-secure-headers/)
- [Mozilla SSL Configuration Generator](https://ssl-config.mozilla.org/)
- [Let's Encrypt - Free SSL Certificates](https://letsencrypt.org/)

---

## Reporting Security Issues

If you discover a security vulnerability, please email security@stormcloud.dev (or create a private security advisory on GitHub).

**Do not** create public issues for security vulnerabilities.
