---
title: Share Links API
published: 2025-12-11
modified: 2025-12-11
tags:
  - api
  - storage
  - share
---

**Version:** 1.0
**Base URL:** `http://localhost:8000/api/v1`
**Authentication:** API Key (CLI) or JWT (Web UI - coming soon)

---

## Overview

Share links allow users to create public URLs for their files with optional password protection, expiration, and custom slugs. The API tracks views and downloads separately.

---

## Authentication

All authenticated endpoints require:

```http
Authorization: Bearer YOUR-API-KEY
```

Public endpoints (file access) require no authentication.

---

## Endpoints

### 1. Create Share Link

**POST** `/api/v1/shares/`

Create a public share link for a file.

**Request Body:**

```json
{
  "file_path": "documents/report.pdf",
  "expiry_days": 7,
  "password": "optional-password",
  "custom_slug": "my-report"
}
```

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file_path` | string | ✅ | Path to the file (must exist) |
| `expiry_days` | integer | ❌ | Days until expiration. Options: `1`, `3`, `7`, `30`, `90`, `0` (never). Default: `7` |
| `password` | string | ❌ | Password protection (hashed server-side) |
| `custom_slug` | string | ❌ | Custom URL slug (3-64 chars, alphanumeric + hyphens) |

**Response:** `201 Created`

```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "owner": 42,
  "file_path": "documents/report.pdf",
  "token": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "custom_slug": "my-report",
  "url": "/api/v1/public/my-report/",
  "has_password": true,
  "expiry_days": 7,
  "expires_at": "2025-12-18T12:00:00Z",
  "created_at": "2025-12-11T12:00:00Z",
  "view_count": 0,
  "download_count": 0,
  "last_accessed_at": null,
  "is_active": true,
  "is_expired": false
}
```

**Errors:**

| Status | Code | Description |
|--------|------|-------------|
| 400 | `VALIDATION_ERROR` | Invalid slug format or duplicate |
| 403 | `FORBIDDEN` | Not authenticated |
| 404 | `FILE_NOT_FOUND` | File doesn't exist |

---

### 2. List Share Links

**GET** `/api/v1/shares/`

Get all share links for the authenticated user.

**Response:** `200 OK`

Returns an array of share link objects, ordered by `created_at` descending (newest first).

---

### 3. Get Share Link Details

**GET** `/api/v1/shares/{share_id}/`

Get details for a specific share link.

**Errors:**

| Status | Code | Description |
|--------|------|-------------|
| 404 | `NOT_FOUND` | Link doesn't exist or belongs to another user |

---

### 4. Revoke Share Link

**DELETE** `/api/v1/shares/{share_id}/`

Revoke (soft-delete) a share link. The link becomes inaccessible immediately.

**Response:** `200 OK`

```json
{
  "message": "Share link revoked",
  "id": "123e4567-e89b-12d3-a456-426614174000"
}
```

**Notes:**
- Soft delete: Sets `is_active = false`
- Link cannot be un-revoked (create a new one instead)
- Public access immediately returns 404

---

### 5. Get Public Share Info

**GET** `/api/v1/public/{token}/`

Get information about a shared file (public, no authentication).

**Headers (optional):**

```http
X-Share-Password: password-if-protected
```

**Response:** `200 OK`

```json
{
  "name": "report.pdf",
  "size": 2048576,
  "content_type": "application/pdf",
  "requires_password": false,
  "download_url": "/api/v1/public/my-report/download/"
}
```

**Errors:**

| Status | Code | Description |
|--------|------|-------------|
| 401 | `PASSWORD_REQUIRED` | Password needed but not provided |
| 401 | `INVALID_PASSWORD` | Wrong password |
| 404 | `SHARE_NOT_FOUND` | Link expired, revoked, or doesn't exist |

**Notes:**
- Token can be UUID or custom slug
- Increments `view_count` on success
- Rate limited: 60 requests/minute per IP

---

### 6. Download Shared File

**GET** `/api/v1/public/{token}/download/`

Download the shared file (public, no authentication).

**Headers (optional):**

```http
X-Share-Password: password-if-protected
```

**Response:** `200 OK` (file stream)

```http
Content-Type: application/pdf
Content-Disposition: attachment; filename="report.pdf"
```

**Errors:**

| Status | Code | Description |
|--------|------|-------------|
| 401 | `PASSWORD_REQUIRED` | Password needed but not provided |
| 401 | `INVALID_PASSWORD` | Wrong password |
| 403 | `DOWNLOAD_DISABLED` | Downloads disabled for this link |
| 404 | `SHARE_NOT_FOUND` | Link expired, revoked, or doesn't exist |
| 404 | `FILE_NOT_FOUND` | File was deleted from storage |

**Notes:**
- Increments `download_count` on success (not view_count)
- Rate limited: 30 requests/minute per IP
- Streams file efficiently (doesn't load into memory)

---

## Rate Limits

| Endpoint | Limit | Scope |
|----------|-------|-------|
| Public share info | 60/min | Per IP address |
| Public download | 30/min | Per IP address |
| Authenticated endpoints | 1000/hour | Per user |

Rate limit exceeded returns `429 Too Many Requests`.

---

## Field Reference

### Share Link Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Unique identifier |
| `owner` | integer | User ID who created the link |
| `file_path` | string | Path to the file |
| `token` | UUID | Auto-generated access token |
| `custom_slug` | string\|null | Custom URL slug (if set) |
| `url` | string | Public access URL (uses slug or token) |
| `has_password` | boolean | Whether password protection is enabled |
| `expiry_days` | integer | Expiration setting (`0` = never) |
| `expires_at` | datetime\|null | Expiration timestamp (null if unlimited) |
| `created_at` | datetime | When link was created |
| `view_count` | integer | Number of times info was viewed |
| `download_count` | integer | Number of times file was downloaded |
| `last_accessed_at` | datetime\|null | Last view or download time |
| `is_active` | boolean | Whether link is active (false = revoked) |
| `is_expired` | boolean | Whether link has expired |

---

## Implementation Examples

### Creating a Share Link (TypeScript)

```typescript
async function createShareLink(
  filePath: string,
  options: {
    expiryDays?: 1 | 3 | 7 | 30 | 90 | 0;
    password?: string;
    customSlug?: string;
  } = {}
) {
  const response = await fetch('http://localhost:8000/api/v1/shares/', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${getApiKey()}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      file_path: filePath,
      expiry_days: options.expiryDays ?? 7,
      password: options.password,
      custom_slug: options.customSlug,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error.message);
  }

  return await response.json();
}
```

### Accessing Public Share

```typescript
async function downloadSharedFile(token: string, password?: string) {
  const headers: Record<string, string> = {};

  if (password) {
    headers['X-Share-Password'] = password;
  }

  const response = await fetch(
    `http://localhost:8000/api/v1/public/${token}/download/`,
    { headers }
  );

  if (!response.ok) {
    throw new Error('Download failed');
  }

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = response.headers
    .get('Content-Disposition')
    ?.split('filename=')[1]
    ?.replace(/"/g, '') || 'file';
  a.click();
  window.URL.revokeObjectURL(url);
}
```

---

## Notes

1. **URL Format**: Public share URLs use either the custom slug OR the UUID token:
   - With slug: `/api/v1/public/my-report/`
   - Without slug: `/api/v1/public/a1b2c3d4-e5f6-7890-abcd-ef1234567890/`

2. **Password Header**: Password is sent via `X-Share-Password` header, NOT in the URL or body

3. **Analytics**:
   - `view_count` = info endpoint calls
   - `download_count` = download endpoint calls
   - They increment independently

4. **Expiry vs Revoke**:
   - Expired links: `is_expired = true`, but still visible in list
   - Revoked links: `is_active = false`, still visible in list
   - Both return 404 on public access

5. **Slug Validation**: Client-side validation recommended: `^[a-zA-Z0-9-]{3,64}$`
