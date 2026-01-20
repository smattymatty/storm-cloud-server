# Storm Cloud Server

Your files, your server, your rules.

Storm Cloud is a self-hosted cloud storage backend. Think Dropbox or Google Drive, but you own it. Upload files, share them with links, manage everything through an API. There's also a markdown CMS baked in if you want to publish content.

Built with Django 6.0 and DRF. Part of the [Storm Developments](https://stormdevelopments.ca) stack.

## Why?

Cloud storage shouldn't require trusting someone else's server. Storm Cloud gives you:

- **File storage with an API** — Upload, download, organize. All the basics.
- **Share links** — Public URLs with optional passwords and expiry dates.
- **Admin controls** — Per-user quotas, permissions, audit logs.
- **CLI-first design** — The API is meant to be scripted. No GraphQL nonsense.
- **Filesystem is truth** — The database is just an index. Delete the DB, rebuild it from disk.

## Quick Start

```bash
git clone https://github.com/stormdevelopments/storm-cloud-server.git
cd storm-cloud-server
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.template .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

API docs at `http://127.0.0.1:8000/api/schema/swagger-ui/`

## Basic Usage

```bash
# Get an API key
python manage.py generate_api_key youruser --name "my-key"

# Upload a file
curl -X POST http://localhost:8000/api/v1/files/notes.md/upload/ \
  -H "Authorization: Bearer YOUR-API-KEY" \
  -F "file=@notes.md"

# Share it (expires in 7 days)
curl -X POST http://localhost:8000/api/v1/shares/ \
  -H "Authorization: Bearer YOUR-API-KEY" \
  -H "Content-Type: application/json" \
  -d '{"file_path": "notes.md", "expiry_days": 7}'

# Anyone can download via the share link (no auth)
curl http://localhost:8000/api/v1/public/abc123/download/ -o notes.md
```

## Project Structure

```
_core/      # Django settings
accounts/   # Users, API keys, auth
storage/    # Files, shares
core/       # Storage backends, utilities
cms/        # Markdown rendering (WIP)
api/v1/     # All the endpoints
```

Full API reference is in the Swagger docs.

## Configuration

Copy `.env.template` to `.env`. The important bits:

- `SECRET_KEY` — Required in production
- `DATABASE_URL` — Defaults to SQLite, use Postgres for real deployments
- `STORMCLOUD_MAX_UPLOAD_SIZE_MB` — Default 100MB
- `STORMCLOUD_ALLOW_REGISTRATION` — Off by default (admin creates users)

See `.env.template` for everything else.

## Deployment

There's a Makefile and Ansible playbook for VPS deployment with Docker. `make deploy` does the thing.

## Status

Core storage and sharing works. The markdown CMS is still being built out. A CLI client is planned.

## License

MIT
