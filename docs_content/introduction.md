---
title: Introduction
published: 2025-12-11
modified: 2025-12-11
tags:
  - intro
  - overview
---

Open-source cloud storage server with markdown CMS capabilities.

---

## What is Storm Cloud?

Storm Cloud Server is a **self-hosted cloud storage solution** designed for developers who want:

- **File Storage** - Upload, download, organize files via REST API
- **CLI-First** - Designed for command-line workflows
- **Markdown CMS** - Built-in SpellBook markdown rendering
- **API Keys** - Simple, secure authentication for programmatic access
- **Public Sharing** - Share files via password-protected links
- **Open Source** - MIT licensed, modify as needed

---

## Architecture

Storm Cloud follows a **modular monolith** architecture:

- **Accounts** - User management, authentication, API keys
- **Storage** - File CRUD operations, share links
- **CMS** - Markdown rendering via Django SpellBook
- **Core** - Shared utilities, storage backends, base models

See [Architecture Decision Records](../architecture/records/) for detailed design decisions.

---

## Key Features

### File Storage
- Upload/download files via REST API
- Directory organization with pagination
- Path traversal protection
- User-isolated storage paths
- Pluggable storage backend (local filesystem, future: S3)

### Share Links
- Public file sharing with unique URLs
- Optional password protection
- Configurable expiry (1, 3, 7, 30, 90 days, or unlimited)
- Custom slugs for user-friendly URLs
- Access analytics (view count, download count)
- Anonymous rate limiting

### Authentication
- **API Keys** - For CLI and programmatic access
- **JWT Tokens** - For web dashboard (coming soon)
- Email verification (optional)
- Password reset flow
- Throttling on all auth endpoints

### CMS
- Markdown file rendering via SpellBook
- Custom SpellBlock components
- Version control ready (files are just markdown)

---

## Technology Stack

- **Backend**: Django 5.2 + Django REST Framework
- **Database**: PostgreSQL
- **Storage**: Local filesystem (S3/Backblaze coming)
- **Authentication**: API Keys + JWT (SimpleJWT)
- **Docs**: Django SpellBook markdown renderer
- **Performance**: Django Mercury monitoring
- **Deployment**: Docker + Docker Compose

---

## Use Cases

### Personal Cloud
Replace Dropbox/Google Drive with your own infrastructure:
```bash
stormcloud upload vacation-photos/
stormcloud share vacation-photos/sunset.jpg --expiry 30
```

### Developer Workflows
Integrate cloud storage into your apps:
```python
import requests

response = requests.post(
    'https://cloud.example.com/api/v1/files/backup.zip/upload/',
    headers={'Authorization': f'Bearer {api_key}'},
    files={'file': open('backup.zip', 'rb')}
)
```

### Static Site Assets
Host files for your website:
```html
<img src="https://cloud.example.com/api/v1/public/my-logo/download/" />
```

### Team File Sharing
Share files with password protection:
```bash
stormcloud share sensitive-doc.pdf --password "team2025" --expiry 7
# Share the link: https://cloud.example.com/api/v1/public/sensitive-doc/
```

---

## Design Philosophy

1. **CLI-First** - API design optimized for command-line usage
2. **Simple Over Clever** - Straightforward code, minimal abstractions
3. **Flat API Responses** - Easy to parse in shell scripts
4. **Type Hints Everywhere** - Python 3.12+ type safety
5. **Test Coverage** - Every endpoint has comprehensive tests

---

## Current Status

**Version:** Alpha (in active development)

**Complete:**
- ✅ Authentication system (18 endpoints, full test coverage)
- ✅ Storage system (7 endpoints, pagination, path security)
- ✅ Share links (5 endpoints, public access, analytics)

**In Progress:**
- 🚧 Content management system (markdown rendering)
- 🚧 CLI client

**Planned:**
- 📋 Web dashboard
- 📋 Backblaze B2 backend
- 📋 Custom SpellBlocks
- 📋 Advanced permissions
- 📋 File versioning
- 📋 Storage quotas
- 📋 Server-side encryption

---

## Quick Links

- [Setup Guide](setup.md) - Get started in 5 minutes
- [Storage API](storage/files.md) - File upload/download docs
- [Share Links API](share-links-api.md) - Public sharing docs
- [Accounts API](accounts/authentication.md) - Auth endpoints
- [Architecture Decisions](../architecture/records/) - Design rationale

---

## License

MIT License - See [LICENSE](../LICENSE) for details.

---

## Contributing

This is an open-source project. Contributions welcome!

1. Fork the repository
2. Create a feature branch
3. Write tests for new functionality
4. Submit a pull request

See [CONTRIBUTING.md](../CONTRIBUTING.md) for detailed guidelines.
