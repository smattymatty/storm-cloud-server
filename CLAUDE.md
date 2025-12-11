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
stormcloud cms add/remove/list/render
stormcloud health ping/status
```

API responses should map cleanly to these commands.

## Not Building Yet

- Web dashboard
- Backblaze B2 backend
- Custom SpellBlocks
- File sharing/permissions
- Versioning
- Quotas
- Encryption (metadata in place, implementation pending)

## Related Libraries

- Django Spellbook - CMS rendering
- Django Mercury - Performance testing

## Style

- Type hints everywhere
- Flat API responses (CLI-friendly)
- Simple over clever