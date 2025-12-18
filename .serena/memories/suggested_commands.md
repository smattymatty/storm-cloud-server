# Storm Cloud Server - Suggested Commands

## Environment Setup

### Virtual Environment (REQUIRED)
```bash
# Create virtual environment
python -m venv venv

# Activate (Linux/macOS)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

**IMPORTANT**: Always activate the virtual environment before running any commands!

## Development Server

### Local Development
```bash
# Activate venv first!
source venv/bin/activate

# Run development server (uses _core.settings.dev + SQLite)
python manage.py runserver

# Access API documentation
# http://127.0.0.1:8000/api/schema/swagger-ui/
```

### Docker Development
```bash
# First-time setup (creates .env, generates secrets)
make setup

# Build and start containers
make up

# View logs
make logs

# Open shell in web container
make shell

# Stop containers
make down

# Restart containers
make restart
```

## Database Management

### Migrations
```bash
# Create migrations after model changes
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Show migration status
python manage.py showmigrations

# Docker:
make migrate
```

### Index Rebuild (Filesystem-Database Sync)
```bash
# Audit mode - report discrepancies only
python manage.py rebuild_index --mode audit

# Sync mode - add missing DB records from filesystem
python manage.py rebuild_index --mode sync

# Clean mode - delete orphaned DB records (requires --force)
python manage.py rebuild_index --mode clean --force

# Full mode - sync + clean (requires --force)
python manage.py rebuild_index --mode full --force

# Target specific user
python manage.py rebuild_index --mode sync --user-id 123

# Preview changes without applying
python manage.py rebuild_index --mode sync --dry-run

# Verbose output
python manage.py rebuild_index --mode audit -v 2

# Helper script:
./scripts/rebuild-index.sh --mode audit
```

## User Management

### Create Users
```bash
# Create superuser (interactive)
python manage.py createsuperuser

# Create test user with API key
python manage.py create_test_user myuser --verified --admin

# Docker:
make superuser
```

### API Keys
```bash
# Generate API key for user
python manage.py generate_api_key username --name "my-key"

# Revoke API key by ID
python manage.py revoke_api_key --id <key-uuid>

# List API keys for user (via Django shell)
python manage.py shell
>>> from accounts.models import APIKey
>>> APIKey.objects.filter(user__username='username')

# Docker:
make api_key
```

### Token Cleanup
```bash
# Clean up expired email verification tokens
python manage.py cleanup_expired_tokens
```

## Testing

### Run Tests
```bash
# Activate venv first!
source venv/bin/activate

# Run all tests
python manage.py test

# Run specific app tests
python manage.py test accounts
python manage.py test storage
python manage.py test core

# Run specific test file
python manage.py test accounts.tests.test_api_keys

# Run specific test case
python manage.py test accounts.tests.test_api_keys.APIKeyTests.test_create_api_key

# Verbose output
python manage.py test -v 2

# Keep test database for inspection
python manage.py test --keepdb
```

### Coverage Analysis
```bash
# Run tests with coverage
coverage run --source='.' manage.py test

# Generate coverage report (terminal)
coverage report

# Generate HTML coverage report
coverage html
# Open htmlcov/index.html in browser

# Coverage for specific app
coverage run --source='accounts' manage.py test accounts
coverage report
```

## Type Checking

### MyPy
```bash
# Check entire codebase
mypy .

# Check specific module
mypy accounts/
mypy storage/api.py

# Show error codes
mypy . --show-error-codes

# Verbose output
mypy . -v
```

## Code Quality

### Django Check
```bash
# Run Django system checks
python manage.py check

# Check for deployment issues
python manage.py check --deploy
```

## Backup & Restore

### Backup
```bash
# Backup database and uploads (Docker)
./scripts/backup.sh

# Manual database backup (PostgreSQL)
docker exec stormcloud_db pg_dump -U stormcloud stormcloud > backup.sql

# Manual SQLite backup
cp db.sqlite3 db.sqlite3.backup
```

### Restore
```bash
# Restore from backup (Docker)
./scripts/restore.sh

# Manual PostgreSQL restore
docker exec -i stormcloud_db psql -U stormcloud stormcloud < backup.sql
```

## Production Deployment

### Ansible Deployment
```bash
# Initial setup - create config
cp deploy/config.example.yml deploy/config.yml
nano deploy/config.yml

# Full deployment
make deploy

# Dry-run (check what would change)
make deploy-check

# Update application only
make deploy-app

# Update nginx configuration only
make deploy-nginx

# Renew SSL certificates
make deploy-ssl
```

### Docker Compose (Manual)
```bash
# Build images
docker compose build

# Start services
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down
```

## GoToSocial Integration

### Setup
```bash
# Create GoToSocial user (if not auto-created by deployment)
make gotosocial-user

# Generate API token for Django integration
make gotosocial-token
```

## Utility Commands

### Django Shell
```bash
# Interactive Python shell with Django environment
python manage.py shell

# Example: Query users
>>> from django.contrib.auth import get_user_model
>>> User = get_user_model()
>>> User.objects.all()

# Example: Check storage usage
>>> from accounts.models import UserProfile
>>> profile = UserProfile.objects.get(user__username='username')
>>> print(f"Used: {profile.storage_used_mb}MB, Quota: {profile.storage_quota_mb}MB")
```

### Database Shell
```bash
# SQLite
python manage.py dbshell

# PostgreSQL (Docker)
docker exec -it stormcloud_db psql -U stormcloud stormcloud
```

### Clean Environment
```bash
# Remove all containers, volumes, and images (DESTRUCTIVE!)
make clean
```

## Git Workflow

### Standard Development
```bash
# Check status
git status

# Stage changes
git add .

# Commit
git commit -m "feat: add feature description"

# Push
git push origin main
```

## Common Tasks Checklist

### After Pulling Changes
```bash
source venv/bin/activate
pip install -r requirements.txt  # Update dependencies
python manage.py migrate         # Apply new migrations
python manage.py test            # Verify tests pass
```

### Before Committing Code
```bash
source venv/bin/activate
python manage.py test            # Run tests
mypy .                           # Check types
python manage.py check           # Django checks
```

### After Model Changes
```bash
python manage.py makemigrations  # Create migration
python manage.py migrate         # Apply migration
python manage.py test            # Verify tests pass
```

## Environment Variables

### Check Configuration
```bash
# Verify .env file exists
cat .env

# Check Django settings being used
python manage.py diffsettings

# Validate environment
./check-env.sh  # Checks required variables
```