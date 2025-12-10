# Storm Cloud Server

Self-hostable cloud storage with API key authentication and markdown CMS capabilities. Built with Django 5.2 and Django REST Framework.

[![Django](https://img.shields.io/badge/django-5.2-blue)](https://www.djangoproject.com/)
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

### Content Management System
- Markdown rendering with Django Spellbook
- Managed content with custom SpellBlocks (in development)

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
| GET | `/api/v1/files/{path}/` | Get file metadata |
| POST | `/api/v1/files/{path}/upload/` | Upload file |
| GET | `/api/v1/files/{path}/download/` | Download file |
| DELETE | `/api/v1/files/{path}/delete/` | Delete file |

### Admin Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/v1/admin/users/` | List/create users |
| GET | `/api/v1/admin/users/{id}/` | Get user details |
| POST | `/api/v1/admin/users/{id}/verify/` | Verify user email |
| POST | `/api/v1/admin/users/{id}/deactivate/` | Deactivate user |
| POST | `/api/v1/admin/users/{id}/activate/` | Activate user |
| GET | `/api/v1/admin/keys/` | List all API keys |
| POST | `/api/v1/admin/keys/{id}/revoke/` | Revoke any API key |

### Health Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health/ping/` | Basic health check |
| GET | `/api/v1/health/status/` | Detailed status with version |

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

### App Structure
```
storm-cloud-server/
├── _core/          # Django project configuration
├── core/           # Base models, storage backends, shared utilities
├── accounts/       # User management, authentication, API keys
├── storage/        # File CRUD operations
├── cms/            # Markdown CMS
└── api/v1/         # Versioned URL routing
```

Architecture decision records available in `/architecture/records/`.

---

## Security

1. **Rate Limiting**: DRF throttling protects against brute force and abuse
   - Login: 5 attempts/minute
   - Registration/API Keys: 10/hour
   - File Uploads: 100/hour
   - File Downloads: 500/hour
   - General API: 1000 requests/hour
2. **Security Event Logging**: All authentication events logged to `logs/security.log`
3. **Email Enumeration Prevention**: Generic responses for email-related endpoints
4. **Soft Delete**: API keys revoked, not deleted (audit trail preserved)
5. **CORS Protection**: Locked down by default
6. **Path Traversal Protection**: Input validation on all file paths
7. **Password Validation**: Django's built-in validators enforced

See [ADR 007: Rate Limiting Strategy](architecture/records/007-rate-limiting-strategy.md) for implementation details.

---

## Project Status

**Current Phase**: Storage implementation complete, CMS in development

- Authentication system: Complete (18 endpoints, comprehensive test coverage)
- Storage system: Complete (7 endpoints, pagination, path security)
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

**Built with Django 5.2 and Django REST Framework**
