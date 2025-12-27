# Storm Cloud Server - Project Overview

## Purpose
Self-hostable cloud storage server with API key authentication and markdown CMS capabilities. Part of the Storm Developments open source stack. Designed with a CLI-first philosophy where the API serves as the backend for command-line tools.

## Tech Stack

### Core Framework
- **Django 6.0** - Web framework
- **Django REST Framework 3.16+** - API framework
- **Python 3.12+** - Programming language

### Key Dependencies
- **drf-spectacular** - OpenAPI/Swagger documentation
- **django-spellbook 0.2.5b2** - Markdown CMS rendering
- **django-mercury-performance 0.1.3b3** - Performance testing
- **gunicorn 22.0+** - Production WSGI server
- **psycopg2-binary** - PostgreSQL adapter
- **whitenoise** - Static file serving
- **python-decouple** - Environment configuration
- **requests** - HTTP library (for external integrations)
- **django-cors-headers** - CORS support

### Type Checking
- **mypy 1.11+** - Static type checker
- **django-stubs 5.1.1+** - Django type stubs
- **djangorestframework-stubs 3.15.1+** - DRF type stubs
- **types-requests** - Requests type stubs

### Testing
- **factory-boy** - Test data factories
- **coverage** - Code coverage reporting

## Architecture

### Design Philosophy
1. **Modular Monolith** - Single Django project with strict app boundaries, no microservices
2. **Pluggable Storage** - Abstract backend interface (local filesystem currently implemented)
3. **API Key Authentication** - Bearer token authentication via `Authorization: Bearer <key>` header
4. **URL Versioning** - All endpoints under `/api/v1/`
5. **CLI-First Design** - API responses optimized for CLI consumption
6. **Filesystem Wins** - Database is rebuildable index, filesystem is source of truth
7. **Encryption Metadata** - All files have encryption metadata (currently `encryption_method='none'`)

### App Structure
- **_core/** - Django project configuration (settings, URLs, WSGI/ASGI)
- **core/** - Base models, storage backends (abstract + local), shared utilities, bulk operations
- **accounts/** - User management, authentication, API keys, admin endpoints
- **storage/** - File CRUD operations, share links
- **cms/** - Spellbook markdown rendering (stub for now)
- **social/** - GoToSocial/ActivityPub integration (federated transparency)
- **api/v1/** - Versioned URL routing
- **docs_app/** - API documentation rendering

### Key Features Implemented
- User registration with email verification
- Session and API key authentication
- File upload/download with multipart support
- Directory management with pagination
- Public share links with password protection and expiry
- Bulk operations (delete, move, copy) for multiple files
- Storage quotas and upload limits
- Admin user management endpoints
- Index rebuild system (filesystem-database sync)
- GoToSocial integration for federated file sharing
- Rate limiting and security event logging

### Features Not Yet Implemented
- Web dashboard
- Backblaze B2 storage backend
- Custom SpellBlocks for CMS
- Advanced permissions beyond basic share links
- File versioning
- Encryption (metadata in place, implementation pending)

## Project Status
**Current Phase**: Storage + sharing complete, CMS in development
- Authentication: ✅ Complete
- Storage: ✅ Complete
- Share Links: ✅ Complete
- Bulk Operations: ✅ Complete
- CMS: 🚧 In Progress
- CLI Client: 📋 Planned