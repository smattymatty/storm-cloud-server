---
title: Setup Guide
published: 2025-12-11
modified: 2025-12-11
tags:
  - setup
  - installation
  - quickstart
---

Get Storm Cloud Server running locally in 5 minutes.

**Architecture:** Storm Cloud uses **Docker + Docker Compose** to orchestrate the web server and PostgreSQL database. The included **Makefile** provides convenient commands for all operations.

---

## Prerequisites

- **Docker** and **Docker Compose** (required)
- **Git** for cloning the repository
- **Make** (pre-installed on Linux/macOS, Windows users can use WSL)

---

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/smattymatty/storm-cloud-server.git
cd storm-cloud-server
```

### 2. First-Time Setup

Run the automated setup script:

```bash
make setup
```

This will:
- Create `.env` file from template
- Generate secure `SECRET_KEY` and `POSTGRES_PASSWORD`
- Set default configuration values

### 3. Build and Start Services

```bash
make build  # Build Docker images
make up     # Start services
```

The `make up` command will:
- Start PostgreSQL container
- Start web server container
- Wait for database to be ready (auto-retries)
- Run migrations automatically
- Collect static files
- Build Spellbook markdown docs
- Start server on `http://localhost:8000`

### 4. Create Admin User

```bash
make superuser
```

Follow the prompts:
```
Username: admin
Email: admin@example.com
Password: ********
Password (again): ********
```

### 5. Generate API Key

```bash
make api_key
```

Enter your username when prompted:
```
Username: admin
✓ API Key created successfully!
Your API key: abc123xyz456...
```

**Save this key!** You'll need it for API access and CLI tools.

---

## Makefile Commands Reference

Run `make` to see all available commands:

```bash
make                 # Show all commands
make setup           # First-time setup (creates .env, generates secrets)
make build           # Build Docker images
make up              # Start services (auto-fixes conflicts)
make down            # Stop services
make restart         # Restart services
make logs            # View logs (interactive menu)
make shell           # Access bash or psql shell (interactive menu)
make superuser       # Create admin user
make api_key         # Generate API key for a user
make ps              # Show container status
make backup          # Backup database + uploads
make restore         # Restore from backup
make clean           # Delete everything (containers, volumes, images)
```

---

## Verify Installation

### Health Check

```bash
curl http://localhost:8000/api/v1/health/status/
```

Expected response:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": 1702324800,
  "uptime": "0h 5m",
  "database": "connected",
  "storage": "local"
}
```

### Test Authentication

```bash
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your-password"}'
```

### Upload a Test File

```bash
curl -X POST http://localhost:8000/api/v1/files/test.txt/upload/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "file=@test.txt"
```

---

## Common Issues

### Docker: Container Exits Immediately

**Problem:** `SECRET_KEY` or `POSTGRES_PASSWORD` not set correctly.

**Solution:** Re-run setup or check `.env`:
```bash
make setup  # Re-generate .env with valid secrets
cat .env | grep SECRET_KEY
cat .env | grep POSTGRES_PASSWORD
```

### Database Connection Refused

**Problem:** PostgreSQL not ready yet.

**Solution:** The entrypoint waits 30 seconds. Check logs:
```bash
make logs  # Select [3] Database only
```

### Port 8000 Already in Use

**Problem:** Another service using port 8000.

**Solution:** Change port in `docker-compose.yml`:
```yaml
ports:
  - "8001:8000"  # Use 8001 instead
```

### Migrations Fail

**Problem:** Database schema out of sync.

**Solution:** Reset database (WARNING: deletes all data):
```bash
make down
docker volume rm storm-cloud-server_postgres_data  # Delete DB volume
make up  # Recreate with fresh database
```

---

## Development Workflow

### View Logs

```bash
make logs
```

Interactive menu:
```
Which logs do you want to view?
  [1] All services (snapshot)
  [2] Web only (snapshot)
  [3] Database only (snapshot)
  [f] Follow all (live)
  [w] Follow web (live)
  [d] Follow database (live)
```

### Access Shell

```bash
make shell
```

Interactive menu:
```
Which shell do you want?
  [1] Web server (bash)
  [2] PostgreSQL (psql)
```

### Run Tests

```bash
# Access web container first
make shell  # Select [1] Web server

# Then run tests
python manage.py test
python manage.py test accounts
python manage.py test storage

# With coverage
coverage run --source='.' manage.py test
coverage report
```

### Check Container Status

```bash
make ps
```

Shows running containers and their health status.

---

## Manual Setup (Without Docker)

**Not Recommended:** Storm Cloud is designed to run with Docker. Manual setup requires more configuration and may have environment-specific issues.

If you must run without Docker:

### 1. Install Dependencies

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Setup PostgreSQL

```sql
CREATE DATABASE stormcloud;
CREATE USER stormcloud WITH PASSWORD 'your-password';
GRANT ALL PRIVILEGES ON DATABASE stormcloud TO stormcloud;
```

### 3. Configure Environment

```bash
cp .env.template .env
# Edit .env with your PostgreSQL credentials
# Set POSTGRES_HOST=localhost
```

### 4. Run Migrations

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 5. Start Development Server

```bash
python manage.py runserver
```

---

## Next Steps

- **API Documentation:** Visit `http://localhost:8000/api/docs/` (Swagger UI)
- **Upload Files:** [Storage API Guide](storage/files.md)
- **Share Links:** [Share Links API](share-links-api.md)
- **Architecture:** [Design Decisions](../architecture/records/)

---

## Production Deployment

For production deployments, see:

- [DOCKER.md](../DOCKER.md) - Production Docker configuration
- [SECURITY.md](../SECURITY.md) - Security best practices

Key production requirements:
- HTTPS via reverse proxy (nginx/Caddy)
- Secure `SECRET_KEY` and `POSTGRES_PASSWORD`
- Set `DEBUG=False`
- Configure SMTP for emails
- Configure automated backups

---

## Backup & Restore

### Create Backup

```bash
make backup
```

Creates timestamped backup in `backups/` directory:
- Database dump (`stormcloud_YYYYMMDD_HHMMSS.sql`)
- Uploaded files (`uploads_YYYYMMDD_HHMMSS.tar.gz`)

### Restore from Backup

```bash
make restore
```

Interactive menu will list available backups.

---

## Getting Help

- **Documentation:** Visit `/api/docs/` on your running server
- **GitHub Issues:** [storm-cloud-server/issues](https://github.com/smattymatty/storm-cloud-server/issues)
- **Make Commands:** Run `make` to see all available commands

---

## Uninstall

### Stop and Remove Everything

```bash
make clean
```

**Warning:** This deletes containers, volumes, and images. All data will be lost.

Manual cleanup:
```bash
make down                                           # Stop containers
docker volume rm storm-cloud-server_postgres_data  # Delete database
docker volume rm storm-cloud-server_uploads        # Delete uploads
docker rmi storm-cloud-server_web                  # Delete image
```
