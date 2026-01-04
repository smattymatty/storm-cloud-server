---
title: Admin File Access API
published: 2025-01-04
modified: 2025-01-04
tags:
  - api
  - storage
  - admin
  - audit
---

Access and manage any user's files with full audit logging.

---

## Overview

Admin users can access, view, upload, download, edit, and delete files in any user's storage. All operations are logged to `FileAuditLog` for compliance and debugging.

**Base URL:** `/api/v1/admin/users/{user_id}/`

**Authentication:** Admin API Key required
```
Authorization: Bearer ADMIN_API_KEY
```

---

## Directory Operations

### List User's Directory

**GET** `/api/v1/admin/users/{user_id}/dirs/` or **GET** `/api/v1/admin/users/{user_id}/dirs/{dir_path}/`

List contents of a user's directory.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | integer | Yes | Target user ID |
| `dir_path` | string | No | Directory path (omit for root) |

**Example Request:**

```bash
# List user's root directory
curl http://localhost:8000/api/v1/admin/users/123/dirs/ \
  -H "Authorization: Bearer ADMIN_API_KEY"

# List subdirectory
curl http://localhost:8000/api/v1/admin/users/123/dirs/documents/projects/ \
  -H "Authorization: Bearer ADMIN_API_KEY"
```

**Example Response:**

```json
{
  "path": "documents",
  "entries": [
    {
      "name": "report.pdf",
      "path": "documents/report.pdf",
      "size": 1048576,
      "is_directory": false,
      "content_type": "application/pdf",
      "modified_at": "2025-01-04T10:00:00Z"
    }
  ],
  "total": 1,
  "target_user": {"id": 123, "username": "alice"}
}
```

---

### Create Directory

**POST** `/api/v1/admin/users/{user_id}/dirs/{dir_path}/create/`

Create a directory in user's storage. Parent directories are created automatically.

**Example Request:**

```bash
curl -X POST http://localhost:8000/api/v1/admin/users/123/dirs/projects/2025/create/ \
  -H "Authorization: Bearer ADMIN_API_KEY"
```

**Example Response:**

```json
{
  "path": "projects/2025",
  "is_directory": true,
  "target_user": {"id": 123, "username": "alice"}
}
```

**Error Codes:**

| Code | Description |
|------|-------------|
| `ALREADY_EXISTS` | Directory already exists |
| `INVALID_PATH` | Invalid path |

---

## File Operations

### Get File Metadata

**GET** `/api/v1/admin/users/{user_id}/files/{file_path}/`

Get metadata about a user's file.

**Example Request:**

```bash
curl http://localhost:8000/api/v1/admin/users/123/files/documents/report.pdf/ \
  -H "Authorization: Bearer ADMIN_API_KEY"
```

**Example Response:**

```json
{
  "path": "documents/report.pdf",
  "name": "report.pdf",
  "size": 1048576,
  "content_type": "application/pdf",
  "is_directory": false,
  "created_at": "2025-01-04T10:00:00Z",
  "modified_at": "2025-01-04T10:00:00Z",
  "encryption_method": "none",
  "target_user": {"id": 123, "username": "alice"}
}
```

---

### Upload File

**POST** `/api/v1/admin/users/{user_id}/files/{file_path}/upload/`

Upload a file to user's storage. Parent directories are created automatically.

**Example Request:**

```bash
curl -X POST http://localhost:8000/api/v1/admin/users/123/files/reports/q4.pdf/upload/ \
  -H "Authorization: Bearer ADMIN_API_KEY" \
  -F "file=@q4-report.pdf"
```

**Example Response:**

```json
{
  "path": "reports/q4.pdf",
  "name": "q4.pdf",
  "size": 2048576,
  "content_type": "application/pdf",
  "is_directory": false,
  "created_at": "2025-01-04T10:00:00Z",
  "modified_at": "2025-01-04T10:00:00Z",
  "encryption_method": "none",
  "target_user": {"id": 123, "username": "alice"}
}
```

---

### Download File

**GET** `/api/v1/admin/users/{user_id}/files/{file_path}/download/`

Download a file from user's storage.

**Example Request:**

```bash
curl http://localhost:8000/api/v1/admin/users/123/files/documents/report.pdf/download/ \
  -H "Authorization: Bearer ADMIN_API_KEY" \
  -o report.pdf
```

**Response:** Binary file stream.

---

### Delete File

**DELETE** `/api/v1/admin/users/{user_id}/files/{file_path}/delete/`

Delete a file or directory from user's storage. Directory deletion is recursive.

**Example Request:**

```bash
# Delete file
curl -X DELETE http://localhost:8000/api/v1/admin/users/123/files/old-file.txt/delete/ \
  -H "Authorization: Bearer ADMIN_API_KEY"

# Delete directory (recursive)
curl -X DELETE http://localhost:8000/api/v1/admin/users/123/files/old-folder/delete/ \
  -H "Authorization: Bearer ADMIN_API_KEY"
```

**Response:** `204 No Content`

**Note:** Deleting files also CASCADE deletes associated ShareLinks.

---

### Preview File Content

**GET** `/api/v1/admin/users/{user_id}/files/{file_path}/content/`

Get raw text content of a user's file for preview. Only works for text-based files.

**Example Request:**

```bash
curl http://localhost:8000/api/v1/admin/users/123/files/readme.md/content/ \
  -H "Authorization: Bearer ADMIN_API_KEY"
```

**Response:** Raw text content.

**Error Codes:**

| Code | Description |
|------|-------------|
| `NOT_TEXT_FILE` | Binary files cannot be previewed |
| `FILE_TOO_LARGE` | Exceeds preview size limit |

---

### Edit File Content

**PUT** `/api/v1/admin/users/{user_id}/files/{file_path}/content/`

Update file content with raw body.

**Example Request:**

```bash
curl -X PUT http://localhost:8000/api/v1/admin/users/123/files/readme.md/content/ \
  -H "Authorization: Bearer ADMIN_API_KEY" \
  -H "Content-Type: text/plain" \
  -d "# Updated Content

New content goes here."
```

**Example Response:**

```json
{
  "detail": "File updated",
  "path": "readme.md",
  "name": "readme.md",
  "size": 42,
  "content_type": "text/markdown",
  "target_user": {"id": 123, "username": "alice"}
}
```

---

## Bulk Operations

**POST** `/api/v1/admin/users/{user_id}/bulk/`

Perform bulk operations on user's files (1-250 paths per request).

**Supported Operations:**
- `delete` - Remove files and directories (recursive)
- `move` - Move files/directories to new location
- `copy` - Duplicate files/directories

**Example Request:**

```bash
# Bulk delete
curl -X POST http://localhost:8000/api/v1/admin/users/123/bulk/ \
  -H "Authorization: Bearer ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"operation":"delete","paths":["old1.txt","old2.txt","archive/"]}'

# Bulk move
curl -X POST http://localhost:8000/api/v1/admin/users/123/bulk/ \
  -H "Authorization: Bearer ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"operation":"move","paths":["file1.txt","file2.txt"],"options":{"destination":"archive"}}'

# Bulk copy
curl -X POST http://localhost:8000/api/v1/admin/users/123/bulk/ \
  -H "Authorization: Bearer ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"operation":"copy","paths":["template.txt"],"options":{"destination":"backup"}}'
```

**Example Response:**

```json
{
  "operation": "delete",
  "total": 3,
  "succeeded": 3,
  "failed": 0,
  "results": [
    {"path": "old1.txt", "success": true},
    {"path": "old2.txt", "success": true},
    {"path": "archive/", "success": true}
  ],
  "target_user": {"id": 123, "username": "alice"}
}
```

---

## File Audit Logging

All admin file operations are automatically logged to `FileAuditLog`.

### Query Audit Logs

**GET** `/api/v1/admin/audit/files/`

Query file operation audit logs with filtering and pagination.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `user_id` | integer | Filter by target user |
| `performed_by` | integer | Filter by admin who performed action |
| `action` | string | Filter by action type |
| `admin_only` | boolean | Only show admin actions (exclude user self-actions) |
| `success` | boolean | Filter by success/failure |
| `path` | string | Filter by path (contains) |
| `from` | datetime | Start date (ISO format) |
| `to` | datetime | End date (ISO format) |
| `page` | integer | Page number |
| `page_size` | integer | Results per page (default 50) |

**Example Requests:**

```bash
# List all audit logs
curl http://localhost:8000/api/v1/admin/audit/files/ \
  -H "Authorization: Bearer ADMIN_API_KEY"

# Filter by target user
curl "http://localhost:8000/api/v1/admin/audit/files/?user_id=123" \
  -H "Authorization: Bearer ADMIN_API_KEY"

# Filter by action type
curl "http://localhost:8000/api/v1/admin/audit/files/?action=delete" \
  -H "Authorization: Bearer ADMIN_API_KEY"

# Filter failures only
curl "http://localhost:8000/api/v1/admin/audit/files/?success=false" \
  -H "Authorization: Bearer ADMIN_API_KEY"

# Date range filter
curl "http://localhost:8000/api/v1/admin/audit/files/?from=2025-01-01T00:00:00Z&to=2025-01-31T23:59:59Z" \
  -H "Authorization: Bearer ADMIN_API_KEY"
```

**Example Response:**

```json
{
  "count": 42,
  "next": "http://localhost:8000/api/v1/admin/audit/files/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "performed_by": 1,
      "target_user": 123,
      "is_admin_action": true,
      "action": "delete",
      "path": "documents/report.pdf",
      "destination_path": null,
      "paths_affected": null,
      "success": true,
      "error_code": null,
      "error_message": null,
      "ip_address": "192.168.1.100",
      "user_agent": "curl/7.68.0",
      "file_size": 1048576,
      "content_type": "application/pdf",
      "created_at": "2025-01-04T10:30:00Z"
    }
  ]
}
```

### Logged Actions

| Action | Description |
|--------|-------------|
| `list` | Directory listing |
| `upload` | File upload |
| `download` | File download |
| `delete` | File/directory deletion |
| `move` | File/directory move |
| `copy` | File/directory copy |
| `edit` | Text file content edit |
| `preview` | Text file content preview |
| `create_dir` | Directory creation |
| `bulk_delete` | Bulk delete operation |
| `bulk_move` | Bulk move operation |
| `bulk_copy` | Bulk copy operation |

### Audit Log Entry Fields

| Field | Description |
|-------|-------------|
| `performed_by` | User ID who performed the action |
| `target_user` | User ID whose files were affected |
| `is_admin_action` | `true` if admin accessing another user's files |
| `action` | One of the action types above |
| `path` | Primary file/directory path |
| `destination_path` | For move/copy operations |
| `paths_affected` | Array of paths for bulk operations |
| `success` | Whether operation succeeded |
| `error_code` | Error code if failed |
| `error_message` | Error message if failed |
| `ip_address` | Client IP address |
| `user_agent` | Client user agent string |
| `file_size` | File size in bytes (for uploads) |
| `content_type` | File content type |
| `created_at` | Timestamp of action |

---

## Error Codes

| Code | Status | Description |
|------|--------|-------------|
| `FILE_NOT_FOUND` | 404 | File doesn't exist |
| `DIRECTORY_NOT_FOUND` | 404 | Directory doesn't exist |
| `ALREADY_EXISTS` | 409 | File/directory already exists |
| `NOT_TEXT_FILE` | 400 | Binary file cannot be previewed |
| `FILE_TOO_LARGE` | 400 | Exceeds size limit |
| `INVALID_PATH` | 400 | Invalid path |
| `INVALID_OPERATION` | 400 | Invalid bulk operation |
| `INVALID_PATHS` | 400 | Invalid paths array |
| `USER_NOT_FOUND` | 404 | Target user doesn't exist |
| `PERMISSION_DENIED` | 403 | Not an admin user |

---

## Security Considerations

1. **Admin Only** - All endpoints require admin authentication
2. **Full Audit Trail** - Every operation is logged with IP, user agent, and timestamp
3. **User Isolation** - Admin must specify target user ID explicitly
4. **Error Logging** - Failed operations are also logged for security monitoring

---

## Next Steps

- [File Storage API](./files.md) - Regular user file operations
- [Bulk Operations](./bulk-operations.md) - Batch file operations
- [Authentication Guide](../accounts/authentication.md) - API key management
