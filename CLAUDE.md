# CLAUDE.md

## Project

Storm Cloud Server - Open source cloud storage with markdown CMS. Django 6.0, DRF.

## Architecture Decisions

1. **Modular Monolith** - Single project, strict app boundaries. No microservices.
2. **Pluggable Storage** - Abstract backend interface. Local filesystem only for now.
3. **API Key Auth** - `Authorization: Bearer <key>` header.
4. **URL Versioning** - All endpoints under `/api/v1/`.
5. **CLI-First** - API serves the CLI. If an endpoint is awkward to consume, fix the API.
6. **Encryption Metadata** - All files have encryption metadata (ADR 006). Currently `encryption_method='none'`. Server-side and client-side encryption will be implemented in future phases.
7. **Filesystem Wins** - Database is rebuildable index (ADR 000, ADR 009). Filesystem is source of truth. Index rebuild available via management command, API, and automated on startup.

## Virtual Environment

This projects `venv/` installs from `requirements.txt` - ensure to activate the venv before shell commands.

## App Structure

- `_core/` - Django project config
- `core/` - Base models, storage backends, shared utilities
- `accounts/` - User management, API keys
- `storage/` - File CRUD
- `cms/` - Spellbook markdown rendering (stub for now)
- `api/v1/` - Versioned URL routing

## CLI Commands (Design Target)
```
stormcloud auth login/logout/whoami
stormcloud files ls/upload/download/rm/info/cat/edit
stormcloud share create/list/revoke/info
stormcloud cms add/remove/list/render
stormcloud health ping/status
stormcloud index audit/sync/clean/full  # Index rebuild operations
```

API responses should map cleanly to these commands.

## File Content Preview/Edit

**Endpoint:** `GET/PUT /api/v1/files/{path}/content/`

Preview and edit text file content inline (without multipart upload or attachment download).

**Preview (GET):**
```bash
# Get file content as plain text
curl /api/v1/files/readme.md/content/ \
  -H "Authorization: Bearer API_KEY"
# Returns: raw text content with Content-Type: text/plain
```

**Edit (PUT):**
```bash
# Update file content with raw body
curl -X PUT /api/v1/files/readme.md/content/ \
  -H "Authorization: Bearer API_KEY" \
  -H "Content-Type: text/plain" \
  -d "# Updated Content"
# Returns: JSON with updated file metadata
```

**Supported File Types (Preview):**
- Text files: `.txt`, `.md`, `.rst`
- Code files: `.py`, `.js`, `.ts`, `.go`, `.rs`, `.java`, `.c`, `.cpp`, etc.
- Config files: `.json`, `.yaml`, `.toml`, `.ini`, `.env`
- Known filenames: `Makefile`, `Dockerfile`, `.gitignore`

**Limits:**
- Preview size limit: Configurable via `STORMCLOUD_MAX_PREVIEW_SIZE_MB` (default 5MB)
- Edit respects global upload limit and per-user quotas
- Edit requires file to exist (use upload endpoint to create new files)

**Error Codes:**
- `NOT_TEXT_FILE` - Binary files cannot be previewed
- `FILE_TOO_LARGE` - Exceeds preview/upload size limit
- `FILE_NOT_FOUND` - File doesn't exist (edit requires existing file)
- `QUOTA_EXCEEDED` - Edit would exceed user quota

## ETag Conditional Caching

**Endpoints:**
- `GET /api/v1/files/{path}/` (info)
- `GET /api/v1/files/{path}/download/`

Both endpoints support HTTP conditional caching via ETag headers. ETags are generated from file metadata (path + size + modified_at), ensuring consistency with "filesystem wins" architecture.

**Response Headers:**
```http
HTTP/1.1 200 OK
ETag: "a1b2c3d4e5f6"
```

**Conditional Request:**
```bash
# Check if cached version is still valid
curl /api/v1/files/photo.jpg/download/ \
  -H "Authorization: Bearer API_KEY" \
  -H 'If-None-Match: "a1b2c3d4e5f6"'

# Returns 304 Not Modified if unchanged (no body)
# Returns 200 with new ETag if changed
```

**Two-Step Optimization Pattern:**
```bash
# 1. Lightweight metadata check
curl /api/v1/files/gallery/photo.jpg/ \
  -H "Authorization: Bearer API_KEY"
# → 200 OK, ETag: "abc123", size: 2.4MB

# 2. Conditional download (skip if unchanged)
curl /api/v1/files/gallery/photo.jpg/download/ \
  -H "Authorization: Bearer API_KEY" \
  -H 'If-None-Match: "abc123"'
# → 304 Not Modified (no body, no file I/O)
```

This is especially useful for large files - clients can check freshness without the server opening the file handle.

## Index Rebuild System

The filesystem-database sync system ensures the database index stays accurate.

### Usage

**Management Command:**
```bash
# Audit mode (default) - report discrepancies only
python manage.py rebuild_index --mode audit

# Sync mode - add missing DB records from filesystem
python manage.py rebuild_index --mode sync

# Clean mode - delete orphaned DB records (requires --force)
python manage.py rebuild_index --mode clean --force

# Full mode - sync + clean (requires --force)
python manage.py rebuild_index --mode full --force

# Options
--user-id 123      # Target specific user
--dry-run          # Preview changes without applying
-v 2               # Verbose output
```

**Helper Script:**
```bash
# Quick audit
./scripts/rebuild-index.sh

# Sync with preview
./scripts/rebuild-index.sh --mode sync --dry-run

# Full reconciliation
./scripts/rebuild-index.sh --mode full --force --verbose
```

**API Endpoint (Admin Only - P0-1):**
```bash
# NOTE: Requires admin API key as of P0-1 security fix
# Audit
curl -X POST /api/v1/index/rebuild/ \
  -H "Authorization: Bearer ADMIN_API_KEY" \
  -d '{"mode":"audit"}'

# Sync specific user
curl -X POST /api/v1/index/rebuild/ \
  -H "Authorization: Bearer ADMIN_API_KEY" \
  -d '{"mode":"sync","user_id":123}'
```

**Automated:** Index audit runs automatically on container startup (see `entrypoint.sh`)

### Modes

- **audit** - Report missing/orphaned records, make no changes
- **sync** - Add missing DB records for files on disk, update stale metadata
- **clean** - Delete orphaned DB records (requires `--force`), CASCADE deletes related ShareLinks
- **full** - Sync + clean (requires `--force`)

### CASCADE Deletion Behavior

**Filesystem Wins (Absolute):** When `clean` or `full` mode deletes an orphaned StoredFile record, Django automatically CASCADE deletes related ShareLinks. This is intentional - ShareLinks pointing to non-existent files are invalid.

Example:
```bash
$ python manage.py rebuild_index --mode clean --force

INFO: Deleting 'beans.txt' (will CASCADE delete 1 ShareLink(s))
INFO: Deleting 'bonko1.png' (will CASCADE delete 1 ShareLink(s))

✓ Records deleted: 9
```

**Why CASCADE?** Filesystem is source of truth. If file doesn't exist, its metadata (StoredFile + ShareLinks) shouldn't either.

### Safety Features

- Clean/full modes require `--force` flag to prevent accidental data loss
- **Django CASCADE handles related records automatically** - ShareLinks deleted with files
- Dry-run mode available for all operations
- Idempotent operations (safe to run multiple times)
- Filesystem always wins - database updates to match disk

## Bulk File Operations

**Endpoint:** `POST /api/v1/bulk/`

Perform operations on multiple files/folders in a single API request. Supports partial success - individual failures don't abort the entire batch.

**Supported Operations:**
- `delete` - Remove files and directories (recursive)
- `move` - Move files/directories to new location
- `copy` - Duplicate files/directories

**Request Format:**
```json
{
  "operation": "delete|move|copy",
  "paths": ["file1.txt", "folder/file2.txt"],
  "options": {
    "destination": "target/path"  // Required for move/copy
  }
}
```

**Limits:**
- 1-250 paths per request
- Operations >50 paths run async (when Django Tasks available)
- Duplicate paths automatically deduplicated

**Response (Sync):**
```json
{
  "operation": "delete",
  "total": 5,
  "succeeded": 4,
  "failed": 1,
  "results": [
    {"path": "file1.txt", "success": true},
    {"path": "missing.txt", "success": false, "error_code": "NOT_FOUND", "error_message": "File not found"},
    {"path": "file2.txt", "success": true, "data": {"new_path": "dest/file2.txt"}}
  ]
}
```

**Response (Async):**
```json
{
  "async": true,
  "task_id": "uuid",
  "total": 150,
  "status_url": "/api/v1/bulk/status/{task_id}/"
}
```

**Examples:**
```bash
# Delete multiple files
curl -X POST /api/v1/bulk/ \
  -H "Authorization: Bearer API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"operation":"delete","paths":["old1.txt","old2.txt"]}'

# Move files to folder
curl -X POST /api/v1/bulk/ \
  -H "Authorization: Bearer API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"operation":"move","paths":["file1.txt","file2.txt"],"options":{"destination":"archive"}}'

# Copy with automatic name collision handling
curl -X POST /api/v1/bulk/ \
  -H "Authorization: Bearer API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"operation":"copy","paths":["doc.txt"],"options":{"destination":"backup"}}'
# Creates "backup/doc.txt" or "backup/doc (copy).txt" if collision
```

**Error Codes:**
- `INVALID_PATH` - Path validation failed (e.g., traversal attempt)
- `NOT_FOUND` - File doesn't exist
- `DESTINATION_NOT_FOUND` - Target directory doesn't exist
- `ALREADY_EXISTS` - File exists at destination (move only)
- `QUOTA_EXCEEDED` - Copy would exceed user quota
- `DELETE_FAILED` / `MOVE_FAILED` / `COPY_FAILED` - Filesystem errors

**Design Notes:**
- Follows "filesystem wins" - operations execute on filesystem first, then DB updated
- Copy operations respect per-user storage quotas
- Move handles name collisions with error (delete existing or rename source first)
- Copy handles name collisions with " (copy)" suffix
- Recursive delete for directories (all contents deleted)
- ShareLinks CASCADE deleted when file deleted

---

## Security & Quotas (P0 Fixes - Dec 2024)

**File Upload Limits:**
- Default max upload: 100MB (configurable via `STORMCLOUD_MAX_UPLOAD_SIZE_MB`)
- Per-user quotas: Admins can set storage quotas via `PATCH /api/v1/admin/users/{id}/quota/`
- Quota enforcement: Upload endpoint checks quota before accepting files
- Overwrite handling: Calculates delta (new size - old size) for replacements

**Admin-Only Endpoints:**
- Index rebuild API (`POST /api/v1/index/rebuild/`) requires admin authentication
- Password reset endpoint blocked until email is configured (security fix)

**Settings:**
```bash
# .env
STORMCLOUD_MAX_UPLOAD_SIZE_MB=100  # Global upload limit
```

**Admin APIs:**
```bash
# Set user quota (MB)
curl -X PATCH /api/v1/admin/users/123/quota/ \
  -H "Authorization: Bearer ADMIN_KEY" \
  -d '{"storage_quota_mb": 500}'

# View user storage usage
curl /api/v1/admin/users/123/ \
  -H "Authorization: Bearer ADMIN_KEY"
# Returns: storage_used_mb, storage_quota_mb, profile.permissions

# Update user permissions
curl -X PATCH /api/v1/admin/users/123/permissions/ \
  -H "Authorization: Bearer ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"can_upload": false, "can_delete": false, "max_share_links": 5}'
```

## Admin File Access

Admins can access and manage any user's files. All admin file operations are logged to `FileAuditLog` for compliance and debugging.

**Base URL:** `/api/v1/admin/users/{user_id}/`

### Directory Operations

```bash
# List user's root directory
curl /api/v1/admin/users/123/dirs/ \
  -H "Authorization: Bearer ADMIN_KEY"

# List subdirectory
curl /api/v1/admin/users/123/dirs/documents/projects/ \
  -H "Authorization: Bearer ADMIN_KEY"

# Create directory
curl -X POST /api/v1/admin/users/123/dirs/new-folder/create/ \
  -H "Authorization: Bearer ADMIN_KEY"
```

### File Operations

```bash
# Get file metadata
curl /api/v1/admin/users/123/files/report.pdf/ \
  -H "Authorization: Bearer ADMIN_KEY"

# Download file
curl /api/v1/admin/users/123/files/report.pdf/download/ \
  -H "Authorization: Bearer ADMIN_KEY" -o report.pdf

# Upload file to user's storage
curl -X POST /api/v1/admin/users/123/files/docs/report.pdf/upload/ \
  -H "Authorization: Bearer ADMIN_KEY" \
  -F "file=@report.pdf"

# Delete file (recursive for directories)
curl -X DELETE /api/v1/admin/users/123/files/old-file.txt/delete/ \
  -H "Authorization: Bearer ADMIN_KEY"

# Preview text file content
curl /api/v1/admin/users/123/files/readme.md/content/ \
  -H "Authorization: Bearer ADMIN_KEY"

# Edit text file content
curl -X PUT /api/v1/admin/users/123/files/readme.md/content/ \
  -H "Authorization: Bearer ADMIN_KEY" \
  -H "Content-Type: text/plain" \
  -d "# Updated content"
```

### Bulk Operations

```bash
# Bulk delete user's files
curl -X POST /api/v1/admin/users/123/bulk/ \
  -H "Authorization: Bearer ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"operation":"delete","paths":["old1.txt","old2.txt"]}'

# Bulk move
curl -X POST /api/v1/admin/users/123/bulk/ \
  -H "Authorization: Bearer ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"operation":"move","paths":["file1.txt"],"options":{"destination":"archive"}}'

# Bulk copy
curl -X POST /api/v1/admin/users/123/bulk/ \
  -H "Authorization: Bearer ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"operation":"copy","paths":["template.txt"],"options":{"destination":"backup"}}'
```

**Response includes `target_user` context:**
```json
{
  "operation": "delete",
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "results": [...],
  "target_user": {"id": 123, "username": "alice"}
}
```

---

## File Audit Logging

All admin file operations are logged to `FileAuditLog` for compliance, debugging, and security monitoring.

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

### Query Audit Logs

```bash
# List all audit logs (paginated)
curl /api/v1/admin/audit/files/ \
  -H "Authorization: Bearer ADMIN_KEY"

# Filter by target user
curl "/api/v1/admin/audit/files/?user_id=123" \
  -H "Authorization: Bearer ADMIN_KEY"

# Filter by admin who performed action
curl "/api/v1/admin/audit/files/?performed_by=1" \
  -H "Authorization: Bearer ADMIN_KEY"

# Filter by action type
curl "/api/v1/admin/audit/files/?action=delete" \
  -H "Authorization: Bearer ADMIN_KEY"

# Filter admin-only actions (exclude user self-actions)
curl "/api/v1/admin/audit/files/?admin_only=true" \
  -H "Authorization: Bearer ADMIN_KEY"

# Filter by success/failure
curl "/api/v1/admin/audit/files/?success=false" \
  -H "Authorization: Bearer ADMIN_KEY"

# Filter by path (contains)
curl "/api/v1/admin/audit/files/?path=documents" \
  -H "Authorization: Bearer ADMIN_KEY"

# Filter by date range
curl "/api/v1/admin/audit/files/?from=2024-01-01T00:00:00Z&to=2024-12-31T23:59:59Z" \
  -H "Authorization: Bearer ADMIN_KEY"

# Pagination
curl "/api/v1/admin/audit/files/?page=2&page_size=50" \
  -H "Authorization: Bearer ADMIN_KEY"
```

### Audit Log Entry Fields

```json
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
  "created_at": "2024-12-15T10:30:00Z"
}
```

### Key Fields

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
| `error_code` | Error code if failed (e.g., `FILE_NOT_FOUND`) |
| `ip_address` | Client IP address |
| `user_agent` | Client user agent string |

---

## User Permission Flags

Granular per-user permissions stored on `UserProfile`:

| Permission | Default | Description |
|------------|---------|-------------|
| `can_upload` | `true` | Upload new files |
| `can_delete` | `true` | Delete files/folders |
| `can_move` | `true` | Move/rename files/folders |
| `can_overwrite` | `true` | Overwrite/edit existing files |
| `can_create_shares` | `true` | Create share links |
| `max_share_links` | `0` | Max active share links (0 = unlimited) |
| `max_upload_bytes` | `0` | Per-file upload limit (0 = use server default) |

**Error Response (403):**
```json
{
  "error": {
    "code": "PERMISSION_DENIED",
    "message": "You do not have permission to perform this action.",
    "permission": "can_delete"
  }
}
```

## Not Building Yet

- Backblaze B2 backend
- Custom SpellBlocks
- Versioning
- Encryption (metadata in place, implementation pending)

## Related Libraries

- Django Spellbook - CMS rendering
- Django Mercury - Performance testing

## Style

- Type hints everywhere
- Flat API responses (CLI-friendly)
- Simple over clever