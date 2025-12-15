---
title: File Storage API
published: 2025-12-11
modified: 2025-12-14
tags:
  - api
  - storage
  - files
---

Upload, download, list, and manage files via REST API.

---

## Overview

The Storage API provides CRUD operations for files stored in your Storm Cloud instance. All operations are user-isolated - you can only access your own files.

**Base URL:** `/api/v1/files/`

**Authentication:** API Key required
```
Authorization: Bearer YOUR_API_KEY
```

---

## Endpoints

### List Files

**GET** `/api/v1/dirs/` or **GET** `/api/v1/dirs/{dir_path}/`

List files and directories.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `dir_path` | string | No | Directory path to list (omit for root) |

**Example Request:**

```bash
# List root directory
curl http://localhost:8000/api/v1/dirs/ \
  -H "Authorization: Bearer YOUR_API_KEY"

# List subdirectory
curl http://localhost:8000/api/v1/dirs/documents/ \
  -H "Authorization: Bearer YOUR_API_KEY"
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
      "modified_at": "2025-12-11T10:00:00Z",
      "encryption_method": "none"
    },
    {
      "name": "notes.txt",
      "path": "documents/notes.txt",
      "size": 2048,
      "is_directory": false,
      "content_type": "text/plain",
      "modified_at": "2025-12-11T09:30:00Z",
      "encryption_method": "none"
    }
  ],
  "total": 2
}
```

---

### Create Empty File

**POST** `/api/v1/files/{file_path}/create/`

Create an empty file at the specified path. Parent directories are automatically created if they don't exist.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | Yes | Destination path (e.g., `documents/notes.txt`) |

**Example Request:**

```bash
curl -X POST http://localhost:8000/api/v1/files/documents/notes.txt/create/ \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**Example Response:**

```json
{
  "detail": "File created",
  "path": "documents/notes.txt",
  "name": "notes.txt",
  "size": 0,
  "content_type": "text/plain",
  "is_directory": false,
  "created_at": "2025-12-14T10:00:00Z",
  "modified_at": "2025-12-14T10:00:00Z",
  "encryption_method": "none"
}
```

**Error Codes:**

| Code | Description |
|------|-------------|
| `ALREADY_EXISTS` | File already exists at this path |
| `INVALID_PATH` | Invalid path (e.g., `../etc/passwd`) |

**Notes:**
- Content type is auto-detected from file extension
- Parent directories are created automatically
- Returns 409 Conflict if file already exists

---

### Upload File

**POST** `/api/v1/files/{file_path}/upload/`

Upload a file to the specified path.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | Yes | Destination path (e.g., `documents/report.pdf`) |

**Request Body:**

Multipart form data with `file` field.

**Example Request:**

```bash
curl -X POST http://localhost:8000/api/v1/files/documents/report.pdf/upload/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "file=@/path/to/local/report.pdf"
```

**Example Response:**

```json
{
  "path": "documents/report.pdf",
  "name": "report.pdf",
  "size": 1048576,
  "content_type": "application/pdf",
  "is_directory": false,
  "created_at": "2025-12-11T10:00:00Z",
  "modified_at": "2025-12-11T10:00:00Z",
  "encryption_method": "none"
}
```

**Error Codes:**

| Code | Description |
|------|-------------|
| `FILE_REQUIRED` | No file provided in request |
| `PATH_TRAVERSAL_DETECTED` | Invalid path (e.g., `../etc/passwd`) |
| `FILE_ALREADY_EXISTS` | File exists at this path (delete first or upload to different path) |

---

### Download File

**GET** `/api/v1/files/{file_path}/download/`

Download a file from storage.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | Yes | File path to download |

**Example Request:**

```bash
curl http://localhost:8000/api/v1/files/documents/report.pdf/download/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -o report.pdf
```

**Response:**

Binary file stream with appropriate `Content-Type` and `Content-Disposition` headers.

**Error Codes:**

| Code | Description |
|------|-------------|
| `FILE_NOT_FOUND` | File does not exist at this path |
| `PATH_TRAVERSAL_DETECTED` | Invalid path |

---

### File Info

**GET** `/api/v1/files/{file_path}/`

Get metadata about a file without downloading it.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | Yes | File path to query |

**Example Request:**

```bash
curl http://localhost:8000/api/v1/files/documents/report.pdf/ \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**Example Response:**

```json
{
  "path": "documents/report.pdf",
  "name": "report.pdf",
  "size": 1048576,
  "content_type": "application/pdf",
  "is_directory": false,
  "created_at": "2025-12-11T10:00:00Z",
  "modified_at": "2025-12-11T10:00:00Z",
  "encryption_method": "none"
}
```

---

### Delete File

**DELETE** `/api/v1/files/{file_path}/delete/`

Delete a file from storage.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | Yes | File path to delete |

**Example Request:**

```bash
curl -X DELETE http://localhost:8000/api/v1/files/documents/old-report.pdf/delete/ \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**Example Response:**

```json
{
  "message": "File deleted successfully",
  "path": "documents/old-report.pdf"
}
```

**Note:** Deleting a file also deletes all associated share links (CASCADE).

---

## API Differences from Typical REST

Storm Cloud uses an unusual but CLI-friendly API design:

- **No `/api/v1/files/` list endpoint** - Use `/api/v1/dirs/` instead
- **Action-based URLs** - `/upload/`, `/download/`, `/delete/` suffixes
- **No PUT/PATCH for updates** - Delete and re-upload instead
- **Flat responses** - No nested objects, easy to parse in shell scripts

This design prioritizes command-line usability over REST conventions.

---

## Path Structure

### Valid Paths

- `file.txt` - Root level
- `documents/report.pdf` - Single directory
- `projects/2025/january/notes.md` - Nested directories

### Invalid Paths

- `../etc/passwd` - Path traversal (rejected)
- `/absolute/path` - Absolute paths (rejected)
- `file?.txt` - Special characters (may fail)

### Best Practices

- Use forward slashes `/` for directory separation
- Avoid spaces in filenames (use hyphens or underscores)
- Use descriptive names: `project-proposal.pdf` not `doc.pdf`
- Organize with directories: `invoices/2025/january.pdf`

---

## No Pagination

Directory listings return **all entries** in a single response. No pagination is currently implemented.

```bash
# Get all files in directory
curl http://localhost:8000/api/v1/dirs/documents/ \
  -H "Authorization: Bearer KEY"
```

**Response structure:**
- `path` - Directory path
- `entries` - Array of all files/subdirectories
- `total` - Count of entries

For large directories, consider organizing files into subdirectories.

---

## Content Types

Storm Cloud automatically detects content types:

| Extension | Content-Type |
|-----------|--------------|
| `.txt` | `text/plain` |
| `.pdf` | `application/pdf` |
| `.jpg`, `.jpeg` | `image/jpeg` |
| `.png` | `image/png` |
| `.json` | `application/json` |
| `.zip` | `application/zip` |

Unknown extensions default to `application/octet-stream`.

---

## Encryption Metadata

All files have an `encryption_method` field:

- `"none"` - Currently the only supported value
- Future: `"server-side-aes256"`, `"client-side-age"`

This field is reserved for future encryption features. See [ADR 006](../../architecture/records/006-encryption-metadata.md) for design details.

---

## Storage Backend

Files are stored using a pluggable backend system:

- **Default:** Local filesystem in `uploads/` directory
- **Future:** Backblaze B2, AWS S3, custom backends

See [ADR 002](../../architecture/records/002-storage-backend.md) for architecture details.

---

## Rate Limits

| Endpoint | Rate Limit |
|----------|------------|
| List | 60 requests/minute |
| Upload | 30 requests/minute |
| Download | 60 requests/minute |
| Info | 100 requests/minute |
| Replace | 30 requests/minute |
| Delete | 30 requests/minute |

Limits are per API key.

---

## Error Handling

All errors follow this format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description",
    "details": {}
  }
}
```

### Common Error Codes

| Code | Status | Description |
|------|--------|-------------|
| `FILE_NOT_FOUND` | 404 | File doesn't exist |
| `FILE_REQUIRED` | 400 | No file in upload request |
| `FILE_ALREADY_EXISTS` | 409 | File exists (use replace) |
| `PATH_TRAVERSAL_DETECTED` | 400 | Invalid path |
| `UNAUTHORIZED` | 401 | Missing/invalid API key |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |

---

## Examples

### Python

```python
import requests

API_KEY = "your-api-key-here"
BASE_URL = "http://localhost:8000/api/v1"

headers = {"Authorization": f"Bearer {API_KEY}"}

# Upload
with open("document.pdf", "rb") as f:
    response = requests.post(
        f"{BASE_URL}/files/documents/document.pdf/upload/",
        headers=headers,
        files={"file": f}
    )
print(response.json())

# Download
response = requests.get(
    f"{BASE_URL}/files/documents/document.pdf/download/",
    headers=headers
)
with open("downloaded.pdf", "wb") as f:
    f.write(response.content)

# List directory
response = requests.get(
    f"{BASE_URL}/dirs/documents/",
    headers=headers
)
files = response.json()["entries"]
```

### JavaScript/TypeScript

```typescript
const API_KEY = "your-api-key-here";
const BASE_URL = "http://localhost:8000/api/v1";

// Upload
const uploadFile = async (file: File, path: string) => {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(
    `${BASE_URL}/files/${path}/upload/`,
    {
      method: "POST",
      headers: { "Authorization": `Bearer ${API_KEY}` },
      body: formData
    }
  );
  return await response.json();
};

// Download
const downloadFile = async (path: string) => {
  const response = await fetch(
    `${BASE_URL}/files/${path}/download/`,
    { headers: { "Authorization": `Bearer ${API_KEY}` } }
  );
  const blob = await response.blob();

  // Create download link
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = path.split("/").pop() || "download";
  a.click();
};

// List directory
const listFiles = async (dirPath: string = "") => {
  const url = dirPath
    ? `${BASE_URL}/dirs/${dirPath}/`
    : `${BASE_URL}/dirs/`;
  const response = await fetch(url, {
    headers: { "Authorization": `Bearer ${API_KEY}` }
  });
  const data = await response.json();
  return data.entries; // Array of files
};
```

### Bash/CLI

```bash
API_KEY="your-api-key-here"
BASE_URL="http://localhost:8000/api/v1"

# Upload
curl -X POST "$BASE_URL/files/backup.zip/upload/" \
  -H "Authorization: Bearer $API_KEY" \
  -F "file=@backup.zip"

# Download
curl "$BASE_URL/files/backup.zip/download/" \
  -H "Authorization: Bearer $API_KEY" \
  -o restored-backup.zip

# List directory
curl "$BASE_URL/dirs/" \
  -H "Authorization: Bearer $API_KEY" \
  | jq '.entries[].path'

# Delete
curl -X DELETE "$BASE_URL/files/old-file.txt/delete/" \
  -H "Authorization: Bearer $API_KEY"
```

---

## Next Steps

- [Share Links API](../share-links-api.md) - Create public download links
- [Authentication Guide](../accounts/authentication.md) - Get your API key
- [CLI Tool](../cli-usage.md) - Use the `stormcloud` CLI
