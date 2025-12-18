# Storm Cloud Server - Codebase Structure

## Top-Level Organization

```
storm-cloud-server/
├── _core/              # Django project configuration
├── accounts/           # User management & authentication
├── api/                # Versioned API routing
├── cms/                # Content Management System
├── core/               # Shared utilities & storage backends
├── docs_app/           # API documentation
├── docs_content/       # User documentation (markdown)
├── social/             # GoToSocial integration
├── storage/            # File operations & share links
├── architecture/       # Architecture Decision Records (ADRs)
├── deploy/             # Ansible deployment scripts
├── scripts/            # Shell scripts (backup, restore, setup)
├── manage.py           # Django management entry point
├── requirements.txt    # Python dependencies
├── pyproject.toml      # MyPy configuration
├── Makefile            # Common development tasks
├── docker-compose.yml  # Docker services
├── Dockerfile          # Web container image
├── .env.template       # Environment variable template
└── README.md           # Project documentation
```

## Core Apps

### _core/ - Django Project Configuration
Django project settings and URL routing.

```
_core/
├── settings/
│   ├── __init__.py
│   ├── base.py          # Shared settings
│   ├── dev.py           # Development (SQLite, DEBUG=True)
│   └── production.py    # Production (PostgreSQL, security)
├── storage_root/        # Local file storage (user data)
│   └── {user_id}/       # Per-user directories
├── __init__.py
├── asgi.py              # ASGI entry point
├── urls.py              # Root URL configuration
└── wsgi.py              # WSGI entry point
```

**Key Settings:**
- `base.py` - Database, installed apps, middleware, DRF config, throttling
- `dev.py` - SQLite, console email, relaxed security
- `production.py` - PostgreSQL, SMTP email, security headers

### accounts/ - User Management & Authentication
User registration, email verification, API keys, admin endpoints.

```
accounts/
├── management/commands/   # CLI commands
│   ├── create_test_user.py
│   ├── generate_api_key.py
│   ├── revoke_api_key.py
│   └── cleanup_expired_tokens.py
├── migrations/           # Database migrations
├── tests/                # Test files
├── __init__.py
├── admin.py             # Django admin config
├── api.py               # API endpoints (21 views)
├── apps.py              # App configuration
├── authentication.py    # API key authentication backend
├── models.py            # User, UserProfile, APIKey, EmailVerificationToken
├── serializers.py       # DRF serializers
├── signal_handlers.py   # Signal receivers
├── signals.py           # Custom signals
├── utils.py             # Helper functions
└── views.py             # Non-API views
```

**Key Models:**
- `User` - Django built-in user model (extended via UserProfile)
- `UserProfile` - Storage usage, quotas, preferences
- `APIKey` - API authentication tokens (Bearer tokens)
- `EmailVerificationToken` - Email verification tokens

**API Endpoints (21 total):**
- Registration, login, logout, email verification
- API key management (create, list, revoke)
- Account management (deactivate, delete)
- Admin user management (create, verify, quota)
- Admin API key management

### storage/ - File Operations & Share Links
File CRUD, directories, public share links, bulk operations.

```
storage/
├── management/commands/
│   └── rebuild_index.py    # Filesystem-database sync
├── migrations/
├── tests/
├── __init__.py
├── admin.py
├── api.py                  # File & share link endpoints
├── apps.py
├── models.py               # File, ShareLink
├── serializers.py
├── tasks.py                # Async tasks (future)
├── utils.py                # File operation helpers
└── views.py
```

**Key Models:**
- `File` - File metadata (path, size, encryption, timestamps)
- `ShareLink` - Public sharing with password, expiry, analytics

**API Endpoints:**
- File operations: upload, download, delete, info
- Directory operations: list, create
- Share links: create, list, revoke, public access
- Bulk operations: delete, move, copy (1-250 files)

### core/ - Shared Utilities & Storage Backends
Base models, storage backend abstraction, shared services.

```
core/
├── services/
│   ├── __init__.py
│   ├── bulk.py            # Bulk file operations
│   └── index_sync.py      # Filesystem-database sync
├── storage/
│   ├── __init__.py
│   ├── base.py            # Abstract storage interface
│   └── local.py           # Local filesystem backend
├── tests/
├── __init__.py
├── admin.py
├── apps.py
├── exceptions.py          # Custom exceptions
├── models.py              # Abstract base models
├── throttling.py          # Rate limiting classes
├── utils.py               # Path validation, normalization
└── views.py               # Base views
```

**Key Components:**
- `core.storage.base.StorageBackend` - Abstract storage interface
- `core.storage.local.LocalStorageBackend` - Filesystem implementation
- `core.utils.normalize_path()` - Path sanitization
- `core.utils.validate_filename()` - Filename validation
- `core.services.bulk.BulkService` - Multi-file operations
- `core.services.index_sync.IndexSyncService` - Database-filesystem sync

### cms/ - Content Management System
Markdown rendering with Django Spellbook (stub implementation).

```
cms/
├── migrations/
├── __init__.py
├── admin.py
├── api.py
├── apps.py
├── models.py       # ManagedContent (stub)
├── serializers.py
└── views.py
```

**Status:** In development, basic structure in place.

### social/ - GoToSocial Integration
ActivityPub integration for federated file sharing transparency.

```
social/
├── management/commands/
│   ├── setup_gotosocial.py
│   └── test_gotosocial_connection.py
├── tests/
├── __init__.py
├── admin.py
├── apps.py
├── client.py          # GoToSocial API client
├── exceptions.py      # Social-specific exceptions
├── middleware.py      # Request middleware
├── models.py          # Social models
├── signals.py         # Signal handlers
└── utils.py           # Helper functions
```

**Key Features:**
- Auto-post share links to Fediverse
- ActivityPub integration
- Graceful degradation if social server unavailable

### api/v1/ - Versioned API Routing
Central API URL routing for version 1.

```
api/v1/
├── __init__.py
└── urls.py    # Aggregates all app API URLs
```

**URL Structure:**
- `/api/v1/auth/*` - Authentication endpoints
- `/api/v1/files/*` - File operations
- `/api/v1/dirs/*` - Directory operations
- `/api/v1/shares/*` - Share link management
- `/api/v1/public/*` - Public share access
- `/api/v1/bulk/*` - Bulk operations
- `/api/v1/admin/*` - Admin endpoints
- `/api/v1/health/*` - Health checks
- `/api/v1/index/*` - Index rebuild

## Supporting Directories

### architecture/ - Architecture Decision Records
Documents key architectural decisions.

```
architecture/records/
├── 000-risk-matrix.md
├── 001-service-granularity.md
├── 002-storage-backend-strategy.md
├── 003-authentication-model.md
├── 004-API-versioning-strategy.md
├── 005-cli-first-development-strategy.md
├── 006-encryption-strategy.md
├── 007-rate-limiting.md
├── 008-federated-read-model.md
└── 009-filesystem-database-sync.md
```

### deploy/ - Ansible Deployment
Production deployment automation.

```
deploy/
├── ansible/
│   ├── templates/           # Jinja2 templates (nginx, env)
│   ├── check-galaxy-deps.sh # Dependency checker
│   ├── inventory.yml        # Ansible inventory
│   ├── playbook.yml         # Main playbook
│   └── requirements.yml     # Galaxy roles
├── config.example.yml       # Example configuration
└── README.md
```

### scripts/ - Shell Scripts
Utility scripts for common operations.

```
scripts/
├── backup.sh          # Backup database and uploads
├── rebuild-index.sh   # Filesystem-database sync
├── restore.sh         # Restore from backup
└── setup.sh           # First-time setup
```

### docs_content/ - User Documentation
Markdown documentation for users.

```
docs_content/
├── accounts/
│   └── authentication.md
├── social/
│   └── gotosocial.md
├── storage/
│   ├── bulk-operations.md
│   └── files.md
├── api-quickstart.md
├── introduction.md
├── setup.md
└── share-links-api.md
```

## File Patterns

### Python Files
- `models.py` - Database models
- `api.py` - DRF API views
- `serializers.py` - DRF serializers
- `utils.py` - Utility functions
- `admin.py` - Django admin configuration
- `apps.py` - App configuration
- `tests.py` or `tests/` - Test files
- `signals.py` - Django signals
- `authentication.py` - Auth backends
- `exceptions.py` - Custom exceptions
- `throttling.py` - Rate limiting

### Configuration Files
- `manage.py` - Django CLI entry point
- `pyproject.toml` - MyPy configuration
- `requirements.txt` - Python dependencies
- `.env.template` - Environment variable template
- `Makefile` - Development tasks
- `docker-compose.yml` - Docker services
- `Dockerfile` - Web container image

## Import Guidelines

### Allowed Cross-App Imports
- ✅ `from core.utils import normalize_path`
- ✅ `from core.storage.local import LocalStorageBackend`
- ✅ `from accounts.models import User`
- ✅ `from accounts.authentication import APIKeyAuthentication`

### Avoid Cross-App Imports
- ❌ `from storage.api import FileUploadView` (in accounts)
- ❌ `from accounts.api import LoginView` (in storage)
- ❌ Circular dependencies between apps

### Respect App Boundaries
Each app should be self-contained with clear public interfaces. Use Django's URL routing and DRF's hyperlinked relationships instead of direct imports.