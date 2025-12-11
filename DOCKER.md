# Docker Deployment Guide

Production-ready Docker setup for Storm Cloud Server with PostgreSQL and gunicorn.

## Prerequisites

- **Docker** 20.10+
- **Docker Compose** 2.0+

That's it. No Python, PostgreSQL, or other dependencies needed on the host.

## Quick Start

**TL;DR**: 3 commands, you're done.

```bash
git clone https://github.com/stormdevelopments/storm-cloud-server.git
cd storm-cloud-server
make setup       # Interactive: generates secrets, prompts for password
make up          # Builds images + starts services
make superuser   # Create admin account
make api_key     # Generate API key
```

Done! Access: http://localhost:8000/api/v1/

### Detailed Setup

<details>
<summary>Click for step-by-step explanation</summary>

#### 1. Setup Environment

```bash
make setup
```

This will:
- Create `.env` from template
- Generate a secure `SECRET_KEY` automatically
- Prompt for PostgreSQL password (with confirmation)
- Optionally configure port (defaults to 8000)
- Validate configuration

#### 2. Start Services

```bash
make up
```

This will:
- Build Docker images (first time only)
- Start PostgreSQL + Django containers
- Run database migrations automatically
- Collect static files

Wait ~30 seconds for services to be healthy.

#### 3. Create Admin Account

```bash
make superuser
```

Follow prompts to set username, email, and password.

#### 4. Generate API Key

```bash
make api_key
```

Enter the username you just created. Copy the API key that's generated.

#### 5. Test It

```bash
curl http://localhost:8000/api/v1/health/status/
```

You should see:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "uptime": "0h 2m",
  "database": "connected",
  "storage": "local"
}
```

</details>


## Makefile Commands

The Makefile is **the way** to interact with your containerized server:

```bash
make setup        # First-time interactive setup
make build        # Build Docker images
make up           # Start services (auto-fixes conflicts)
make down         # Stop services
make restart      # Restart services
make logs         # View logs (interactive)
make shell        # Interactive shell (web or postgres)
make superuser    # Create admin account
make api_key      # Generate API key (interactive)
make migrate      # Run database migrations
make backup       # Backup database + uploads
make restore      # Restore from backup (interactive)
make clean        # Delete EVERYTHING (asks for confirmation)
make ps           # Show container status
```

All commands auto-detect whether you have `docker-compose` (v1) or `docker compose` (v2).

## Configuration

### Critical Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `SECRET_KEY` | placeholder | **YES** | Django secret key - MUST change in production |
| `POSTGRES_PASSWORD` | `change-this-secure-password` | **YES** | Database password |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | No | Add your domain for production |

### Security Variables

**📖 See [SECURITY.md](SECURITY.md) for comprehensive security configuration guide.**

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `True` | Set to `False` in production |
| `SECURE_HSTS_SECONDS` | `31536000` | HSTS duration - start with 300 for testing |
| `SESSION_COOKIE_SECURE` | `True` | Require HTTPS for session cookies |
| `CSRF_COOKIE_SECURE` | `True` | Require HTTPS for CSRF cookies |
| `SECURE_SSL_REDIRECT` | `False` | Let reverse proxy handle redirects |
| `STORMCLOUD_ALLOW_REGISTRATION` | `False` | Enable public user registration |
| `STORMCLOUD_REQUIRE_EMAIL_VERIFICATION` | `True` | Require email verification |

### Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `THROTTLE_LOGIN_RATE` | `5/min` | Login attempts per minute |
| `THROTTLE_AUTH_RATE` | `10/hour` | Registration/API key creation per hour |
| `THROTTLE_UPLOAD_RATE` | `100/hour` | File uploads per hour |
| `THROTTLE_DOWNLOAD_RATE` | `500/hour` | File downloads per hour |
| `THROTTLE_USER_RATE` | `1000/hour` | General API requests per hour |

See [.env.template](.env.template) for complete list of configuration options.

### Email Configuration

For production email (password resets, verification), configure SMTP:

```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@example.com
EMAIL_HOST_PASSWORD=your-password
DEFAULT_FROM_EMAIL=noreply@yourdomain.com
```

## Common Operations

### View Logs

```bash
make logs      # Interactive menu: snapshot or follow logs
```

<details>
<summary>Or use docker compose directly</summary>

```bash
docker compose logs -f          # Follow all services
docker compose logs -f web      # Web service only
docker compose logs -f db       # Database only
docker compose logs --tail=100  # Last 100 lines
```
</details>

### Restart Services

```bash
make restart   # Restart all services
```

After changing code or Dockerfile:
```bash
docker compose build
docker compose up -d
docker compose exec web python manage.py migrate
```

### Stop Services

```bash
make down      # Stop all services (keeps data)
make clean     # Delete EVERYTHING (destructive, asks for confirmation)
```

### Backups and Restore

```bash
make backup    # Backup database + uploads (timestamped)
make restore   # Restore from backup (interactive, lists available backups)
```

Backups are stored in `./backups/` with manifest files for easy identification.

<details>
<summary>Manual backup/restore</summary>

```bash
# Backup
docker compose exec db pg_dump -U stormcloud stormcloud > backup.sql
tar -czf uploads-backup.tar.gz uploads/

# Restore
cat backup.sql | docker compose exec -T db psql -U stormcloud -d stormcloud
tar -xzf uploads-backup.tar.gz
```
</details>

### User Management

```bash
make superuser   # Create admin account
make api_key     # Generate API key for a user
make shell       # Interactive shell (web or postgres)
```

### Check Service Health

```bash
make ps          # Container status
make logs        # Interactive log viewer

# Test health endpoint
curl http://localhost:8000/api/v1/health/status/
```

Example response:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "uptime": "2h 34m",
  "database": "connected",
  "storage": "local"
}
```

## Data Persistence

### Upload Files

User uploads are stored in `./uploads/` on the host, mounted into the container.

**Backup uploads:**
```bash
tar -czf uploads-backup-$(date +%Y%m%d).tar.gz uploads/
```

### Database

PostgreSQL data is stored in the `postgres_data` Docker volume.

**Backup database:**
```bash
docker compose exec db pg_dump -U stormcloud stormcloud > stormcloud-backup-$(date +%Y%m%d).sql
```

**Restore database:**
```bash
# Stop web service first
docker compose stop web

# Restore
cat stormcloud-backup-20241210.sql | docker compose exec -T db psql -U stormcloud -d stormcloud

# Start web service
docker compose start web
```

## Upgrading

### Pull Latest Changes

```bash
cd storm-cloud-server
git pull origin main
```

### Rebuild and Restart

```bash
# Rebuild images
docker compose build

# Restart with new image
docker compose up -d

# Check logs for migration output
docker compose logs -f web
```

Migrations run automatically on container start via `entrypoint.sh`.

## Troubleshooting

### Container Won't Start

**Error:** `SECRET_KEY is not set or is still the placeholder value`

**Fix:** Run `make setup` or manually set `SECRET_KEY` in `.env`:
```bash
python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

---

**Error:** `POSTGRES_PASSWORD environment variable is not set`

**Fix:** Set `POSTGRES_PASSWORD` in `.env`:
```bash
POSTGRES_PASSWORD=your-secure-password-here
```

---

**Error:** `Database did not become ready after 30 seconds`

**Fix:** Check database logs:
```bash
docker compose logs db
```

Common causes:
- PostgreSQL container failed to start
- Insufficient disk space
- Corrupted volume (try `docker compose down -v` and restart)

### Health Check Failing

**Symptom:** `docker compose ps` shows `stormcloud_web` as `unhealthy`

**Check logs:**
```bash
docker compose logs web
```

**Test health endpoint manually:**
```bash
docker compose exec web curl http://localhost:8000/api/v1/health/
```

**Common causes:**
- Migrations failed (check entrypoint output)
- Database connection issue (check POSTGRES_* environment variables)
- Application error (check web logs)

### Permission Denied on Uploads

**Error:** Permission denied when uploading files

**Fix:** Ensure uploads directory is writable:
```bash
chmod -R 755 ./uploads
```

### Port Already in Use

**Error:** `Bind for 0.0.0.0:8000 failed: port is already allocated`

**Fix:** Either:
1. Stop the process using port 8000: `lsof -ti:8000 | xargs kill`
2. Change port in `docker-compose.yml`: `"8080:8000"`

### Cannot Connect to Database from Outside Container

**Expected behavior:** The database is intentionally NOT exposed to the host for security.

Only the web container can access it. To connect from your host:

```bash
docker compose exec db psql -U stormcloud -d stormcloud
```

## Production Deployment

This Docker setup is production-ready for self-hosting, but follow these guidelines for internet exposure:

### Reverse Proxy (Required)

Put behind nginx or Caddy for:
- **SSL/TLS** termination
- **HTTP/2** support
- **Static file** serving
- **Rate limiting** at connection level

**Example nginx config:**
```nginx
server {
    listen 443 ssl http2;
    server_name cloud.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /path/to/storm-cloud-server/staticfiles/;
    }
}
```

### Security Checklist

Before exposing to the internet:

#### Required Changes
- [ ] Change `SECRET_KEY` to unique value (in `.env`)
- [ ] Change `POSTGRES_PASSWORD` to strong password (in `.env`)
- [ ] Set `DEBUG=False` in `.env`
- [ ] Update `ALLOWED_HOSTS` with your domain (e.g., `cloud.example.com`)

#### HTTPS/TLS Configuration
- [ ] Configure HTTPS via reverse proxy (nginx/Caddy/Traefik)
- [ ] Obtain SSL certificate (Let's Encrypt recommended)
- [ ] Test HTTPS is working before enabling security settings
- [ ] Verify `SECURE_HSTS_SECONDS` in `.env` (start with 300, increase to 31536000)
- [ ] Confirm `SESSION_COOKIE_SECURE=True` (default, requires HTTPS)
- [ ] Confirm `CSRF_COOKIE_SECURE=True` (default, requires HTTPS)
- [ ] Keep `SECURE_SSL_REDIRECT=False` (reverse proxy handles redirects)

**⚠️ IMPORTANT:** Read [SECURITY.md](SECURITY.md) for detailed explanations of each security setting.

#### Infrastructure Security
- [ ] Set up firewall (only expose 80/443, block 8000)
- [ ] Configure SMTP for email notifications
- [ ] Set up automated backups (database + uploads)
- [ ] Review rate limiting configuration (see `.env.template`)
- [ ] Set up monitoring (health checks, disk space, logs)

#### Validation
- [ ] Run `python manage.py check --deploy` inside container
- [ ] Test login/logout over HTTPS
- [ ] Verify security headers with [securityheaders.com](https://securityheaders.com/)
- [ ] Check SSL configuration with [ssllabs.com](https://www.ssllabs.com/ssltest/)

### Environment Separation

Use different `.env` files for staging/production:

```bash
# Production
docker compose --env-file .env.production up -d

# Staging
docker compose --env-file .env.staging up -d
```

### Scaling Considerations

Single-server deployment is sufficient for most self-hosting needs. If you need to scale:

- Add Redis for distributed rate limiting cache
- Use managed PostgreSQL (RDS, DigitalOcean, etc.)
- Use object storage for uploads (S3, Backblaze B2)
- Run multiple web containers with load balancer

## Support

- **Issues**: https://github.com/stormdevelopments/storm-cloud-server/issues
- **Docs**: See README.md for API documentation
- **ADRs**: See `architecture/records/` for design decisions
