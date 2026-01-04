# Storm Cloud Server

Self-hostable cloud storage with API key authentication and markdown CMS capabilities. Built with Django 6.0 and Django REST Framework.

[![Django](https://img.shields.io/badge/django-6.0-blue)](https://www.djangoproject.com/)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Part of the Storm Developments open source stack.

---

## Features

### Authentication & Authorization
- User registration with email verification
- Session authentication (browser/Swagger UI)
- API key management for programmatic access
- Admin user management endpoints
- Security event logging to `logs/security.log`
- Soft delete for API keys (audit trail preserved)

### File Storage
- File upload/download with multipart support
- Directory creation and listing with pagination
- Path traversal protection
- User-isolated storage paths
- Pluggable storage backend (local filesystem implemented)

### Share Links
- Public file sharing with unique URLs
- Optional password protection
- Configurable expiry (1, 3, 7, 30, 90 days, or unlimited)
- Custom slugs for user-friendly URLs
- Access analytics (view count, last accessed)
- Anonymous rate limiting for public endpoints

### Content Management System
- Markdown rendering with Django Spellbook
- Managed content with custom SpellBlocks (in development)

### Web UI
- Browser-based file management interface
- File upload, download, and organization
- Share link management
- User settings and API key management

---

## Quick Start

### Prerequisites
- Python 3.12+
- Virtual environment

### Installation

```bash
# Clone the repository
git clone https://github.com/stormdevelopments/storm-cloud-server.git
cd storm-cloud-server

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create environment file (optional for development)
cp .env.template .env
# Edit .env with your settings, or use defaults

# Run migrations
python manage.py migrate

# Create a superuser
python manage.py createsuperuser

# Start the development server
python manage.py runserver
```

Visit `http://127.0.0.1:8000/api/schema/swagger-ui/` for interactive API documentation.

---

## API Overview

All endpoints are versioned under `/api/v1/`. Full API documentation available at `/api/schema/swagger-ui/` when running.

### Authentication Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register/` | Register new user |
| POST | `/api/v1/auth/verify-email/` | Verify email with token |
| POST | `/api/v1/auth/login/` | Session login |
| POST | `/api/v1/auth/logout/` | Session logout |
| GET | `/api/v1/auth/me/` | Get current user info |
| GET/POST | `/api/v1/auth/tokens/` | List/create API keys |
| POST | `/api/v1/auth/tokens/{id}/revoke/` | Revoke API key |
| POST | `/api/v1/auth/deactivate/` | Deactivate account |
| DELETE | `/api/v1/auth/delete/` | Delete account |

### Storage Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/dirs/` | List root directory |
| GET | `/api/v1/dirs/{path}/` | List directory contents |
| POST | `/api/v1/dirs/{path}/create/` | Create directory |
| GET | `/api/v1/files/{path}/` | Get file metadata (supports ETag) |
| POST | `/api/v1/files/{path}/upload/` | Upload file |
| GET | `/api/v1/files/{path}/download/` | Download file (supports ETag/If-None-Match) |
| DELETE | `/api/v1/files/{path}/delete/` | Delete file |
| GET | `/api/v1/files/{path}/content/` | Preview text file content |
| PUT | `/api/v1/files/{path}/content/` | Edit text file content |
| POST | `/api/v1/bulk/` | Bulk delete/move/copy operations |

### Index Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/index/rebuild/` | Rebuild database index (admin only) |

### Share Link Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/v1/shares/` | List/create share links (authenticated) |
| GET | `/api/v1/shares/{id}/` | Get share link details (authenticated) |
| DELETE | `/api/v1/shares/{id}/` | Revoke share link (authenticated) |
| GET | `/api/v1/public/{token}/` | Get public share info (no auth) |
| GET | `/api/v1/public/{token}/download/` | Download shared file (no auth) |

### Admin Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/v1/admin/users/` | List/create users |
| GET | `/api/v1/admin/users/{id}/` | Get user details (includes storage usage) |
| POST | `/api/v1/admin/users/{id}/verify/` | Verify user email |
| POST | `/api/v1/admin/users/{id}/deactivate/` | Deactivate user |
| POST | `/api/v1/admin/users/{id}/activate/` | Activate user |
| PATCH | `/api/v1/admin/users/{id}/quota/` | Set user storage quota |
| PATCH | `/api/v1/admin/users/{id}/permissions/` | Update user permissions |
| POST | `/api/v1/admin/users/{id}/keys/` | Create API key for user |
| GET | `/api/v1/admin/keys/` | List all API keys |
| POST | `/api/v1/admin/keys/{id}/revoke/` | Revoke any API key |

### Admin File Access Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/admin/users/{id}/dirs/` | List user's root directory |
| GET | `/api/v1/admin/users/{id}/dirs/{path}/` | List user's subdirectory |
| POST | `/api/v1/admin/users/{id}/dirs/{path}/create/` | Create directory in user's storage |
| GET | `/api/v1/admin/users/{id}/files/{path}/` | Get file metadata |
| POST | `/api/v1/admin/users/{id}/files/{path}/upload/` | Upload file to user's storage |
| GET | `/api/v1/admin/users/{id}/files/{path}/download/` | Download user's file |
| DELETE | `/api/v1/admin/users/{id}/files/{path}/delete/` | Delete user's file (recursive) |
| GET | `/api/v1/admin/users/{id}/files/{path}/content/` | Preview user's text file |
| PUT | `/api/v1/admin/users/{id}/files/{path}/content/` | Edit user's text file |
| POST | `/api/v1/admin/users/{id}/bulk/` | Bulk operations on user's files |
| GET | `/api/v1/admin/audit/files/` | Query file audit logs |

### Health Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health/ping/` | Basic health check |
| GET | `/api/v1/health/status/` | Detailed status with version |

---

## Usage Examples

### Creating and Sharing Files

```bash
# Upload a file
curl -X POST http://127.0.0.1:8000/api/v1/files/document.pdf/upload/ \
  -H "Authorization: Bearer YOUR-API-KEY" \
  -F "file=@/path/to/document.pdf"

# Create a public share link (7 day expiry)
curl -X POST http://127.0.0.1:8000/api/v1/shares/ \
  -H "Authorization: Bearer YOUR-API-KEY" \
  -H "Content-Type: application/json" \
  -d '{"file_path": "document.pdf", "expiry_days": 7}'

# Create password-protected share with custom slug
curl -X POST http://127.0.0.1:8000/api/v1/shares/ \
  -H "Authorization: Bearer YOUR-API-KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "document.pdf",
    "custom_slug": "my-document",
    "password": "secret123",
    "expiry_days": 30
  }'

# Access public share (no authentication required)
curl http://127.0.0.1:8000/api/v1/public/my-document/

# Download shared file with password
curl http://127.0.0.1:8000/api/v1/public/my-document/download/ \
  -H "X-Share-Password: secret123" \
  -o document.pdf

# List your share links
curl http://127.0.0.1:8000/api/v1/shares/ \
  -H "Authorization: Bearer YOUR-API-KEY"

# Revoke a share link
curl -X DELETE http://127.0.0.1:8000/api/v1/shares/{share-id}/ \
  -H "Authorization: Bearer YOUR-API-KEY"
```

---

## Advanced Features

### File Content Preview & Edit

Preview and edit text file content inline without multipart upload or attachment download.

```bash
# Preview file content (returns plain text)
curl http://127.0.0.1:8000/api/v1/files/readme.md/content/ \
  -H "Authorization: Bearer YOUR-API-KEY"

# Edit file content (raw body)
curl -X PUT http://127.0.0.1:8000/api/v1/files/readme.md/content/ \
  -H "Authorization: Bearer YOUR-API-KEY" \
  -H "Content-Type: text/plain" \
  -d "# Updated Content"
```

**Supported file types:** `.txt`, `.md`, `.rst`, `.py`, `.js`, `.ts`, `.go`, `.rs`, `.java`, `.c`, `.cpp`, `.json`, `.yaml`, `.toml`, `.ini`, `.env`, `Makefile`, `Dockerfile`, `.gitignore`, and more.

**Limits:** Preview size configurable via `STORMCLOUD_MAX_PREVIEW_SIZE_MB` (default 5MB).

### ETag Conditional Caching

File info and download endpoints support HTTP conditional caching via ETag headers, reducing bandwidth for unchanged files.

```bash
# First request - get file with ETag
curl -i http://127.0.0.1:8000/api/v1/files/photo.jpg/download/ \
  -H "Authorization: Bearer YOUR-API-KEY"
# Response includes: ETag: "a1b2c3d4e5f6"

# Subsequent request - check if file changed
curl http://127.0.0.1:8000/api/v1/files/photo.jpg/download/ \
  -H "Authorization: Bearer YOUR-API-KEY" \
  -H 'If-None-Match: "a1b2c3d4e5f6"'
# Returns 304 Not Modified if unchanged (no body transferred)
```

### Bulk Operations

Perform operations on multiple files/folders in a single API request (1-250 paths).

```bash
# Delete multiple files
curl -X POST http://127.0.0.1:8000/api/v1/bulk/ \
  -H "Authorization: Bearer YOUR-API-KEY" \
  -H "Content-Type: application/json" \
  -d '{"operation":"delete","paths":["old1.txt","old2.txt","archive/"]}'

# Move files to folder
curl -X POST http://127.0.0.1:8000/api/v1/bulk/ \
  -H "Authorization: Bearer YOUR-API-KEY" \
  -H "Content-Type: application/json" \
  -d '{"operation":"move","paths":["file1.txt","file2.txt"],"options":{"destination":"archive"}}'

# Copy files
curl -X POST http://127.0.0.1:8000/api/v1/bulk/ \
  -H "Authorization: Bearer YOUR-API-KEY" \
  -H "Content-Type: application/json" \
  -d '{"operation":"copy","paths":["doc.txt"],"options":{"destination":"backup"}}'
```

**Operations:** `delete` (recursive for directories), `move`, `copy`

**Response:** Partial success supported - individual failures don't abort the batch.

### Index Rebuild (Filesystem-Database Sync)

The database is a rebuildable index; the filesystem is the source of truth. Use these tools to reconcile discrepancies.

```bash
# Management command
python manage.py rebuild_index --mode audit      # Report only
python manage.py rebuild_index --mode sync       # Add missing DB records
python manage.py rebuild_index --mode clean --force  # Delete orphaned DB records
python manage.py rebuild_index --mode full --force   # Sync + clean

# API endpoint (admin only)
curl -X POST http://127.0.0.1:8000/api/v1/index/rebuild/ \
  -H "Authorization: Bearer ADMIN-API-KEY" \
  -H "Content-Type: application/json" \
  -d '{"mode":"audit"}'
```

**Modes:**
- `audit` - Report discrepancies, make no changes
- `sync` - Add missing DB records for files on disk
- `clean` - Delete orphaned DB records (requires `--force`)
- `full` - Sync + clean (requires `--force`)

Index audit runs automatically on container startup.

### Admin File Access

Admins can access, manage, and audit any user's files. All operations are logged to `FileAuditLog`.

```bash
# List user's files
curl http://127.0.0.1:8000/api/v1/admin/users/123/dirs/ \
  -H "Authorization: Bearer ADMIN-API-KEY"

# Download user's file
curl http://127.0.0.1:8000/api/v1/admin/users/123/files/document.pdf/download/ \
  -H "Authorization: Bearer ADMIN-API-KEY" -o document.pdf

# Upload file to user's storage
curl -X POST http://127.0.0.1:8000/api/v1/admin/users/123/files/reports/q4.pdf/upload/ \
  -H "Authorization: Bearer ADMIN-API-KEY" \
  -F "file=@q4.pdf"

# Delete user's file (recursive for directories)
curl -X DELETE http://127.0.0.1:8000/api/v1/admin/users/123/files/old-folder/delete/ \
  -H "Authorization: Bearer ADMIN-API-KEY"

# Bulk operations on user's files
curl -X POST http://127.0.0.1:8000/api/v1/admin/users/123/bulk/ \
  -H "Authorization: Bearer ADMIN-API-KEY" \
  -H "Content-Type: application/json" \
  -d '{"operation":"move","paths":["file1.txt","file2.txt"],"options":{"destination":"archive"}}'
```

### File Audit Logging

Query audit logs to track all admin file operations.

```bash
# List all audit logs
curl http://127.0.0.1:8000/api/v1/admin/audit/files/ \
  -H "Authorization: Bearer ADMIN-API-KEY"

# Filter by target user
curl "http://127.0.0.1:8000/api/v1/admin/audit/files/?user_id=123" \
  -H "Authorization: Bearer ADMIN-API-KEY"

# Filter by action type
curl "http://127.0.0.1:8000/api/v1/admin/audit/files/?action=delete" \
  -H "Authorization: Bearer ADMIN-API-KEY"

# Filter failures only
curl "http://127.0.0.1:8000/api/v1/admin/audit/files/?success=false" \
  -H "Authorization: Bearer ADMIN-API-KEY"

# Date range filter
curl "http://127.0.0.1:8000/api/v1/admin/audit/files/?from=2024-01-01&to=2024-12-31" \
  -H "Authorization: Bearer ADMIN-API-KEY"
```

**Logged actions:** `list`, `upload`, `download`, `delete`, `move`, `copy`, `edit`, `preview`, `create_dir`, `bulk_delete`, `bulk_move`, `bulk_copy`

**Filter options:** `user_id`, `performed_by`, `action`, `admin_only`, `success`, `path`, `from`, `to`, `page`, `page_size`

### User Quotas & Permissions

Admins can set per-user storage quotas and granular permissions.

```bash
# Set storage quota (MB)
curl -X PATCH http://127.0.0.1:8000/api/v1/admin/users/123/quota/ \
  -H "Authorization: Bearer ADMIN-API-KEY" \
  -H "Content-Type: application/json" \
  -d '{"storage_quota_mb": 500}'

# Update permissions
curl -X PATCH http://127.0.0.1:8000/api/v1/admin/users/123/permissions/ \
  -H "Authorization: Bearer ADMIN-API-KEY" \
  -H "Content-Type: application/json" \
  -d '{"can_upload": true, "can_delete": false, "max_share_links": 10}'
```

**Permission flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `can_upload` | `true` | Upload new files |
| `can_delete` | `true` | Delete files/folders |
| `can_move` | `true` | Move/rename files |
| `can_overwrite` | `true` | Overwrite/edit existing files |
| `can_create_shares` | `true` | Create share links |
| `max_share_links` | `0` | Max active share links (0 = unlimited) |
| `max_upload_bytes` | `0` | Per-file upload limit (0 = server default) |

---

## Authentication

### API Key Authentication (Recommended)

Generate an API key using the management command or web interface:

```bash
# Create API key
python manage.py generate_api_key username --name "my-key"

# Use in requests
curl -H "Authorization: Bearer YOUR-API-KEY" \
  http://127.0.0.1:8000/api/v1/auth/me/
```

### Session Authentication

Login to receive a session cookie:

```bash
curl -c cookies.txt -X POST http://127.0.0.1:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}'

# Use session cookie
curl -b cookies.txt http://127.0.0.1:8000/api/v1/auth/me/
```

---

## Configuration

Storm Cloud uses environment variables for configuration. Copy [.env.template](.env.template) to `.env` and customize:

```bash
cp .env.template .env
```

### Key Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | (dev key) | **REQUIRED for production** - Django secret key |
| `DEBUG` | `True` | Set to `False` in production |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated list of allowed hosts |
| `DATABASE_URL` | `sqlite:///db.sqlite3` | Database connection URL |
| `STORMCLOUD_ALLOW_REGISTRATION` | `False` | Enable public user registration |
| `STORMCLOUD_REQUIRE_EMAIL_VERIFICATION` | `True` | Require email verification |
| `STORMCLOUD_MAX_API_KEYS_PER_USER` | `0` | Max API keys per user (0 = unlimited) |
| `STORMCLOUD_CORS_ORIGINS` | `` | Comma-separated list of allowed CORS origins |
| `THROTTLE_LOGIN_RATE` | `5/min` | Login attempts rate limit |
| `THROTTLE_AUTH_RATE` | `10/hour` | Registration and API key creation limit |
| `THROTTLE_UPLOAD_RATE` | `100/hour` | File upload limit |
| `THROTTLE_DOWNLOAD_RATE` | `500/hour` | File download limit |
| `THROTTLE_USER_RATE` | `1000/hour` | General authenticated API limit |
| `THROTTLE_PUBLIC_SHARE_RATE` | `60/min` | Public share info access limit |
| `THROTTLE_PUBLIC_SHARE_DOWNLOAD_RATE` | `30/min` | Public share download limit |
| `STORMCLOUD_ALLOW_UNLIMITED_SHARE_LINKS` | `True` | Allow unlimited expiry on share links |
| `STORMCLOUD_DEFAULT_SHARE_EXPIRY_DAYS` | `7` | Default expiry for new share links |
| `STORMCLOUD_MAX_UPLOAD_SIZE_MB` | `100` | Maximum file upload size in MB |
| `STORMCLOUD_MAX_PREVIEW_SIZE_MB` | `5` | Maximum file size for content preview |

### Email Configuration

Development uses console backend by default. For production SMTP, set in `.env`:

```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@example.com
EMAIL_HOST_PASSWORD=your-password
DEFAULT_FROM_EMAIL=noreply@yourdomain.com
```

### Database Configuration

For PostgreSQL in production:

```bash
DATABASE_URL=postgresql://user:password@localhost:5432/stormcloud
```

---

## Management Commands

```bash
# Create test user
python manage.py create_test_user username --verified --admin

# Generate API key
python manage.py generate_api_key username --name "cli-key"

# Revoke API key
python manage.py revoke_api_key --id <key-uuid>

# Clean up expired tokens
python manage.py cleanup_expired_tokens

# Rebuild database index from filesystem
python manage.py rebuild_index --mode audit       # Report discrepancies
python manage.py rebuild_index --mode sync        # Add missing records
python manage.py rebuild_index --mode full --force  # Full reconciliation
```

---

## Testing

```bash
# Activate virtual environment
source venv/bin/activate

# Run all tests
python manage.py test

# Run specific app tests
python manage.py test accounts

# Generate coverage report
coverage run --source='.' manage.py test
coverage report
coverage html  # Open htmlcov/index.html
```

---

## Architecture

### Design Principles
- **Modular Monolith**: Single Django project with strict app boundaries
- **Pluggable Backends**: Abstract storage interface for future expansion
- **CLI-First Design**: API responses optimized for command-line consumption
- **URL Versioning**: All endpoints under `/api/v1/`
- **Filesystem Wins**: Database is a rebuildable index; filesystem is source of truth

### App Structure
```
storm-cloud-server/
├── _core/          # Django project configuration
├── core/           # Base models, storage backends, bulk operations, index sync
├── accounts/       # User management, authentication, API keys
├── storage/        # File CRUD operations, share links
├── cms/            # Markdown CMS (Spellbook)
├── social/         # GoToSocial/ActivityPub integration
└── api/v1/         # Versioned URL routing
```

### Architecture Decision Records

| ADR | Title |
|-----|-------|
| [000](architecture/records/000-risk-matrix.md) | Risk Matrix |
| [001](architecture/records/001-service-granularity.md) | Service Granularity (Modular Monolith) |
| [002](architecture/records/002-storage-backend-strategy.md) | Storage Backend Strategy |
| [003](architecture/records/003-authentication-model.md) | Authentication Model |
| [004](architecture/records/004-API-versioning-strategy.md) | API Versioning Strategy |
| [005](architecture/records/005-cli-first-development-strategy.md) | CLI-First Development |
| [006](architecture/records/006-encryption-strategy.md) | Encryption Strategy |
| [007](architecture/records/007-rate-limiting.md) | Rate Limiting |
| [009](architecture/records/009-index-rebuild-strategy.md) | Index Rebuild Strategy |

---

## Security

1. **Rate Limiting**: DRF throttling protects against brute force and abuse
   - Login: 5 attempts/minute
   - Registration/API Keys: 10/hour
   - File Uploads: 100/hour
   - File Downloads: 500/hour
   - General API: 1000 requests/hour
2. **Per-User Quotas**: Storage limits and upload size restrictions per user
3. **Granular Permissions**: Fine-grained control over user capabilities (upload, delete, share, etc.)
4. **Security Event Logging**: All authentication events logged to `logs/security.log`
5. **File Audit Logging**: All admin file operations logged to `FileAuditLog` (IP, user agent, success/failure)
6. **Email Enumeration Prevention**: Generic responses for email-related endpoints
7. **Soft Delete**: API keys revoked, not deleted (audit trail preserved)
8. **CORS Protection**: Locked down by default
9. **Path Traversal Protection**: Input validation on all file paths
10. **Password Validation**: Django's built-in validators enforced
11. **Admin-Only Endpoints**: Sensitive operations (index rebuild, quota management, file access) restricted to admins

See [ADR 007: Rate Limiting Strategy](architecture/records/007-rate-limiting.md) for implementation details.

---

## Project Status

**Current Phase**: Core features complete, CMS in development

- Authentication system: Complete (21 endpoints, comprehensive test coverage)
- Storage system: Complete (file CRUD, bulk operations, content preview/edit)
- Share links: Complete (public access, password protection, analytics)
- User quotas & permissions: Complete
- Index rebuild system: Complete (filesystem-database sync)
- ETag caching: Complete
- Admin file access: Complete (access any user's files with audit logging)
- File audit logging: Complete (track all admin file operations)
- GoToSocial integration: Complete
- Web UI: Complete
- Content management: In progress (markdown rendering with Spellbook)
- CLI client: Planned

---

## Development

### Running the Server

```bash
source venv/bin/activate
python manage.py runserver
```

### Code Style
- Type hints required
- Flat API responses (CLI-friendly)
- Simple over clever
- Follow existing patterns

---

## Related Projects

- **[Django Spellbook](https://github.com/smattymatty/django_spellbook)**: Markdown CMS framework
- **[Django Mercury](https://github.com/80-20-Human-In-The-Loop/Django-Mercury-Performance-Testing)**: API performance testing
- **Storm Cloud CLI**: Command-line client (coming soon)

---

## Contributing

Early stage project - breaking changes expected. Issues and pull requests welcome.

### Guidelines

1. Fork the repository
2. Create a feature branch
3. Write tests for changes
4. Ensure tests pass (`python manage.py test`)
5. Submit pull request

---

## License

MIT License - See [LICENSE](LICENSE) for details.

---

## Contact

For questions or issues, please open an issue on GitHub.

---

**Built with Django 6.0 and Django REST Framework**
