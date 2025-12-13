---
title: API Quickstart
published: 2025-12-12
modified: 2025-12-12
tags:
  - api
  - reference
  - quickstart
  - endpoints
---

Quick reference for all Storm Cloud Server API endpoints and common workflows.

---

## Base URL

```
http://localhost:8000/api/v1
```

In production, replace with your domain:
```
https://your-domain.com/api/v1
```

---

## Authentication

All endpoints (except health checks and public shares) require authentication.

### API Key Authentication (Recommended)

Include your API key in the `Authorization` header:

```bash
Authorization: Bearer YOUR_API_KEY_HERE
```

**Example:**
```bash
curl http://localhost:8000/api/v1/auth/me/ \
  -H "Authorization: Bearer abc123xyz456..."
```

### Session Authentication (Web UI)

For browser-based access, login via `/auth/login/` to get a session cookie.

---

## Quick Start: Complete Workflow

Here's how to register, upload a file, and create a share link:

```bash
# 1. Register an account
curl -X POST http://localhost:8000/api/v1/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "email": "alice@example.com",
    "password": "secure-password-123"
  }'

# 2. Verify email (check your email for token)
curl -X POST http://localhost:8000/api/v1/auth/verify-email/ \
  -H "Content-Type: application/json" \
  -d '{"token": "EMAIL_TOKEN_HERE"}'

# 3. Login to get session
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "password": "secure-password-123"
  }'

# 4. Create API key for CLI access
curl -X POST http://localhost:8000/api/v1/auth/tokens/ \
  -H "Authorization: Bearer SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "My CLI Key"}'

# Save the API key from response!

# 5. Upload a file
curl -X POST http://localhost:8000/api/v1/files/documents/report.pdf/upload/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "file=@report.pdf"

# 6. Create a share link (expires in 7 days, password protected)
curl -X POST http://localhost:8000/api/v1/shares/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "documents/report.pdf",
    "expiry_days": 7,
    "password": "secret123",
    "custom_slug": "report-q4"
  }'

# 7. Share the public URL
# Public access: http://localhost:8000/api/v1/public/report-q4/
```

---

## Endpoint Reference

### Health & Status

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/health/` | None | Basic health check (Docker) |
| GET | `/health/ping/` | None | Alias for health check |
| GET | `/health/status/` | None | Detailed status (DB, uptime, storage) |

**Example:**
```bash
curl http://localhost:8000/api/v1/health/status/
```

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": 1702324800,
  "uptime": "5h 23m",
  "database": "connected",
  "storage": "local"
}
```

---

### Authentication & Registration

#### Account Management

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/auth/register/` | None | Create new account |
| POST | `/auth/verify-email/` | None | Verify email with token |
| POST | `/auth/resend-verification/` | None | Resend verification email |
| POST | `/auth/login/` | None | Login (session auth) |
| POST | `/auth/logout/` | Session | Logout |
| GET | `/auth/me/` | Required | Get current user info |
| POST | `/auth/deactivate/` | Required | Deactivate account |
| DELETE | `/auth/delete/` | Required | Permanently delete account |

#### API Keys (Tokens)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/auth/tokens/` | Required | List your API keys |
| POST | `/auth/tokens/` | Required | Create new API key |
| POST | `/auth/tokens/{key_id}/revoke/` | Required | Revoke an API key |

**Create API Key:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/tokens/ \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "CLI Access"}'
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "CLI Access",
  "key": "abc123xyz456...",
  "created_at": "2025-12-12T10:30:00Z",
  "last_used_at": null
}
```

---

### Files & Directories

#### Directory Operations

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/dirs/` | Required | List root directory |
| GET | `/dirs/{dir_path}/` | Required | List specific directory |
| POST | `/dirs/{dir_path}/create/` | Required | Create directory |

**List Files:**
```bash
curl http://localhost:8000/api/v1/dirs/ \
  -H "Authorization: Bearer YOUR_KEY"
```

**Response:**
```json
{
  "path": "",
  "files": [
    {
      "path": "photo.jpg",
      "size": 2048576,
      "created_at": "2025-12-12T10:00:00Z",
      "is_directory": false
    }
  ],
  "directories": ["documents", "photos"]
}
```

#### File Operations

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/files/{file_path}/upload/` | Required | Upload file |
| GET | `/files/{file_path}/` | Required | Get file metadata |
| GET | `/files/{file_path}/download/` | Required | Download file |
| DELETE | `/files/{file_path}/delete/` | Required | Delete file |

**Upload File:**
```bash
curl -X POST http://localhost:8000/api/v1/files/vacation/beach.jpg/upload/ \
  -H "Authorization: Bearer YOUR_KEY" \
  -F "file=@beach.jpg"
```

**Download File:**
```bash
curl http://localhost:8000/api/v1/files/vacation/beach.jpg/download/ \
  -H "Authorization: Bearer YOUR_KEY" \
  -o beach.jpg
```

---

### Share Links

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/shares/` | Required | List your share links |
| POST | `/shares/` | Required | Create share link |
| GET | `/shares/{share_id}/` | Required | Get share link details |
| PATCH | `/shares/{share_id}/` | Required | Update share link |
| DELETE | `/shares/{share_id}/` | Required | Delete share link |
| GET | `/public/{token}/` | None | Get public share info |
| GET | `/public/{token}/download/` | None | Download via share link |

**Create Share Link:**
```bash
curl -X POST http://localhost:8000/api/v1/shares/ \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "documents/report.pdf",
    "expiry_days": 7,
    "password": "secret123",
    "custom_slug": "q4-report"
  }'
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "file_path": "documents/report.pdf",
  "token": "q4-report",
  "public_url": "http://localhost:8000/api/v1/public/q4-report/",
  "expires_at": "2025-12-19T10:00:00Z",
  "password_protected": true,
  "view_count": 0,
  "download_count": 0,
  "created_at": "2025-12-12T10:00:00Z"
}
```

**Access Public Share:**
```bash
# View share info
curl http://localhost:8000/api/v1/public/q4-report/

# Download file (if password protected, include in request body)
curl -X POST http://localhost:8000/api/v1/public/q4-report/download/ \
  -H "Content-Type: application/json" \
  -d '{"password": "secret123"}' \
  -o report.pdf
```

---

### CMS (Markdown Content)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/cms/` | Required | List managed content |
| POST | `/cms/add/` | Required | Add content to CMS |
| DELETE | `/cms/{content_id}/remove/` | Required | Remove from CMS |
| GET | `/cms/{content_id}/render/` | Required | Render single markdown file |
| POST | `/cms/render/` | Required | Bulk render markdown files |

---

### Admin Endpoints

*Requires staff/admin permissions*

#### User Management

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/admin/users/` | Admin | List all users |
| POST | `/admin/users/` | Admin | Create user (skip email verification) |
| GET | `/admin/users/{user_id}/` | Admin | Get user details |
| PATCH | `/admin/users/{user_id}/` | Admin | Update user |
| POST | `/admin/users/{user_id}/verify/` | Admin | Manually verify user email |
| POST | `/admin/users/{user_id}/deactivate/` | Admin | Deactivate user |
| POST | `/admin/users/{user_id}/activate/` | Admin | Activate user |
| POST | `/admin/users/{user_id}/reset-password/` | Admin | Reset user password |

#### API Key Management

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/admin/keys/` | Admin | List all API keys (all users) |
| POST | `/admin/keys/{key_id}/revoke/` | Admin | Revoke any API key |

#### Storage Management

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/index/rebuild/` | Admin | Rebuild file index |

---

## Rate Limiting

Storm Cloud implements rate limiting to prevent abuse:

| Endpoint | Limit | Window |
|----------|-------|--------|
| `/auth/login/` | 5 requests | 1 minute |
| `/auth/register/` | 3 requests | 1 hour |
| File uploads | 100 requests | 1 hour |
| Public share access | 60 requests | 1 minute |
| General API | 1000 requests | 1 hour |

**Rate limit headers:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1702328400
```

**Rate limit exceeded response:**
```json
{
  "error": "Rate limit exceeded",
  "detail": "Too many requests. Try again in 45 seconds."
}
```

---

## Error Responses

All error responses follow this format:

```json
{
  "error": "Error type",
  "detail": "Human-readable error message"
}
```

### Common HTTP Status Codes

| Code | Meaning | Example |
|------|---------|---------|
| 200 | Success | Request completed successfully |
| 201 | Created | Resource created (file uploaded, share created) |
| 204 | No Content | Deletion successful |
| 400 | Bad Request | Invalid JSON, missing required fields |
| 401 | Unauthorized | Invalid or missing API key |
| 403 | Forbidden | Valid auth but insufficient permissions |
| 404 | Not Found | File or resource doesn't exist |
| 409 | Conflict | Resource already exists (duplicate filename) |
| 413 | Payload Too Large | File exceeds size limit |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Server Error | Internal server error |

---

## Common Workflows

### Upload and Organize Files

```bash
# Create directory structure
curl -X POST http://localhost:8000/api/v1/dirs/projects/website/create/ \
  -H "Authorization: Bearer YOUR_KEY"

# Upload files to directory
curl -X POST http://localhost:8000/api/v1/files/projects/website/index.html/upload/ \
  -H "Authorization: Bearer YOUR_KEY" \
  -F "file=@index.html"

curl -X POST http://localhost:8000/api/v1/files/projects/website/style.css/upload/ \
  -H "Authorization: Bearer YOUR_KEY" \
  -F "file=@style.css"

# List directory contents
curl http://localhost:8000/api/v1/dirs/projects/website/ \
  -H "Authorization: Bearer YOUR_KEY"
```

### Share Multiple Files

```bash
# Upload files
for file in photo1.jpg photo2.jpg photo3.jpg; do
  curl -X POST http://localhost:8000/api/v1/files/vacation/$file/upload/ \
    -H "Authorization: Bearer YOUR_KEY" \
    -F "file=@$file"
done

# Create share links (expires in 30 days)
for file in photo1.jpg photo2.jpg photo3.jpg; do
  curl -X POST http://localhost:8000/api/v1/shares/ \
    -H "Authorization: Bearer YOUR_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"file_path\": \"vacation/$file\", \"expiry_days\": 30}"
done

# List all share links
curl http://localhost:8000/api/v1/shares/ \
  -H "Authorization: Bearer YOUR_KEY"
```

### Manage API Keys

```bash
# Create multiple keys for different purposes
curl -X POST http://localhost:8000/api/v1/auth/tokens/ \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "CLI Access"}'

curl -X POST http://localhost:8000/api/v1/auth/tokens/ \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "Backup Script"}'

# List all keys
curl http://localhost:8000/api/v1/auth/tokens/ \
  -H "Authorization: Bearer YOUR_KEY"

# Revoke a key
curl -X POST http://localhost:8000/api/v1/auth/tokens/{KEY_ID}/revoke/ \
  -H "Authorization: Bearer YOUR_KEY"
```

---

## Interactive API Documentation

Storm Cloud provides interactive API documentation via Swagger UI:

**Swagger UI:** `http://localhost:8000/api/docs/`

Features:
- Try endpoints directly in browser
- Auto-generated from Django REST Framework
- Shows request/response schemas
- Test authentication

---

## Related Documentation

- [Setup Guide](setup.md) - Get Storm Cloud running
- [Authentication Guide](accounts/authentication.md) - Detailed auth docs
- [File Storage API](storage/files.md) - File operations reference
- [Share Links API](share-links-api.md) - Share link reference
- [Production Monitoring](production/monitoring.md) - Sentry integration

---

## Getting Help

- **Interactive Docs:** Visit `/api/docs/` on your running server
- **GitHub Issues:** [storm-cloud-server/issues](https://github.com/smattymatty/storm-cloud-server/issues)
- **Source Code:** Check `api/v1/urls.py` for all endpoints
