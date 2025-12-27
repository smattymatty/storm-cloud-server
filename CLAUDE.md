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
stormcloud files ls/upload/download/rm/info
stormcloud share create/list/revoke/info
stormcloud cms add/remove/list/render
stormcloud health ping/status
stormcloud index audit/sync/clean/full  # Index rebuild operations
```

API responses should map cleanly to these commands.

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
# Returns: storage_used_mb, storage_quota_mb
```

## Not Building Yet

- Web dashboard
- Backblaze B2 backend
- Custom SpellBlocks
- Advanced permissions (basic share links implemented)
- Versioning
- Encryption (metadata in place, implementation pending)

## Related Libraries

- Django Spellbook - CMS rendering
- Django Mercury - Performance testing

## Style

- Type hints everywhere
- Flat API responses (CLI-friendly)
- Simple over clever