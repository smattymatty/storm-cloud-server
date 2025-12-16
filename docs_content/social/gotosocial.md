---
title: GoToSocial Integration
published: 2025-12-16
modified: 2025-12-16
tags:
  - gotosocial
  - fediverse
  - mastodon
  - social
---

Storm Cloud Server includes optional [GoToSocial](https://gotosocial.org/) integration - a lightweight, single-user Fediverse server compatible with Mastodon and other ActivityPub platforms.

---

## Overview

**What is GoToSocial?**

GoToSocial is a self-hosted social media server that speaks ActivityPub. It's designed to be:
- **Lightweight** - Runs on minimal resources (1 CPU, 512MB RAM)
- **Single-user focused** - Perfect for personal instances
- **Mastodon-compatible** - Works with all Mastodon apps and can federate with any ActivityPub server

**Why include it with Storm Cloud?**

- Share your content to the Fediverse directly from your cloud storage
- Own your social presence alongside your files
- Single deployment manages both services

---

## Requirements

Before enabling GoToSocial:

1. **Separate domain/subdomain** - e.g., `social.example.com`
2. **DNS A record** - Point subdomain to your server IP
3. **Storm Cloud deployed** - GoToSocial runs alongside the main application

---

## Setup

### 1. Configure

Edit `deploy/config.yml`:

```yaml
install_gotosocial: true
gotosocial_domain: "social.example.com"  # Your social subdomain
```

### 2. Deploy

```bash
make deploy
```

This will:
- Obtain SSL certificate for your social domain
- Configure nginx reverse proxy
- Start GoToSocial container
- Create data directory for SQLite database and media

### 3. Create User Account

```bash
make gotosocial-user
```

Interactive prompts:
```
═══════════════════════════════════════════════════
  GoToSocial - Create User Account
═══════════════════════════════════════════════════

Username: yourname
Email: you@example.com
Password: ********

Creating account... done
Confirming account... done
Promoting to admin... done
Restarting GoToSocial for admin changes to take effect...

═══════════════════════════════════════════════════
Account created successfully!
═══════════════════════════════════════════════════
```

Note: The account is automatically promoted to admin since GoToSocial is configured as a single-user instance for organizational use.

### 4. Generate API Token (Optional)

If you want Django to post to GoToSocial:

```bash
make gotosocial-token
```

This walks you through the OAuth2 flow:

```
═══════════════════════════════════════════════════
  GoToSocial - Generate API Token
═══════════════════════════════════════════════════

GoToSocial domain (e.g., social.example.com): social.example.com

Step 1: Creating application... done

Step 2: Open this URL in your browser:

  https://social.example.com/oauth/authorize?client_id=xxx&...

  1. Log in with your GoToSocial account
  2. Click "Allow"
  3. Copy the code shown

Paste authorization code: xxxxxxx

Step 3: Exchanging for token... done

═══════════════════════════════════════════════════
  Success! Add these to your .env file:
═══════════════════════════════════════════════════

  GOTOSOCIAL_DOMAIN=social.example.com
  GOTOSOCIAL_TOKEN=your_access_token_here

  Then restart Django: make restart
```

---

## Auto-Posting Share Links

Storm Cloud can automatically post share link announcements to your GoToSocial account.

### Enable Auto-Posting

1. Generate API token (if not already done):
   ```bash
   make gotosocial-token
   ```

2. Add to `.env`:
   ```bash
   GOTOSOCIAL_AUTO_POST_ENABLED=true
   STORMCLOUD_BASE_URL=https://cloud.example.com  # Your public URL
   ```

3. Restart Django:
   ```bash
   make restart
   ```

### How It Works

When you create a share link, Storm Cloud automatically posts to your Fediverse timeline:

```
🔗 New file shared: project-proposal.pdf

📦 2.3 MB
⏰ Expires in 7 days

→ https://cloud.example.com/api/v1/public/abc123/
```

### Customize Post Template

Edit `.env`:
```bash
GOTOSOCIAL_SHARE_TEMPLATE="📄 {file_name} ({file_size})\n{share_url}\n\n#StormCloud"
```

Available variables:
- `{file_name}` - Filename
- `{file_size}` - Human-readable size
- `{expiry}` - Expiration info
- `{password_note}` - 🔒 indicator if password-protected
- `{share_url}` - Full share link URL

### Delete Posts When Links Revoked

Posts are automatically deleted when share links are revoked or expire (enabled by default):

```bash
GOTOSOCIAL_DELETE_ON_REVOKE=true  # Default: true
```

To keep posts even after links expire (maximum transparency):
```bash
GOTOSOCIAL_DELETE_ON_REVOKE=false
```

### Manual Cleanup

Clean up expired posts manually:

```bash
# Dry run (see what would be deleted)
make shell
python manage.py cleanup_expired_social_posts --dry-run

# Actually delete
python manage.py cleanup_expired_social_posts
```

### Set Up Cron Job

On production server, add to crontab for automatic cleanup:

```bash
# Edit crontab
crontab -e

# Add this line (runs daily at 2 AM)
0 2 * * * cd /home/stormcloud/storm-cloud-server && docker compose exec -T web python manage.py cleanup_expired_social_posts
```

---

## Usage

### Access Your Instance

Visit `https://social.example.com` to see your GoToSocial instance.

### Login

GoToSocial doesn't have a web UI for posting. Use a Mastodon-compatible app:

**Mobile:**
- [Tusky](https://tusky.app/) (Android)
- [Ice Cubes](https://apps.apple.com/app/ice-cubes-for-mastodon/id6444915884) (iOS)
- [Megalodon](https://sk22.github.io/megalodon/) (Android)

**Desktop:**
- [Elk](https://elk.zone/) (Web)
- [Pinafore](https://pinafore.social/) (Web)
- [Whalebird](https://whalebird.social/) (Desktop app)

When prompted for instance, enter your domain: `social.example.com`

### Follow Other Accounts

Search for any Fediverse account using their full handle:
```
@user@mastodon.social
@someone@fosstodon.org
```

### Get Followed

Share your handle with others:
```
@yourname@social.example.com
```

---

## Architecture

### How It Runs

```
┌─────────────────────────────────────────────────────────────┐
│                         nginx                                │
│  ┌─────────────────────┐  ┌─────────────────────────────┐   │
│  │ cloud.example.com   │  │ social.example.com          │   │
│  │        :443         │  │        :443                 │   │
│  └──────────┬──────────┘  └──────────────┬──────────────┘   │
└─────────────┼────────────────────────────┼──────────────────┘
              │                            │
              ▼                            ▼
┌─────────────────────────┐  ┌─────────────────────────────┐
│   Storm Cloud (Django)  │  │       GoToSocial            │
│      127.0.0.1:8000     │  │      127.0.0.1:8081         │
│                         │  │                             │
│  ┌───────────────────┐  │  │  ┌───────────────────────┐  │
│  │    PostgreSQL     │  │  │  │   SQLite + Media      │  │
│  │   postgres_data   │  │  │  │   gotosocial_data/    │  │
│  └───────────────────┘  │  └──┴───────────────────────┴──┘
└─────────────────────────┘
         stormcloud_network (Docker bridge)
```

### Container Details

| Service | Image | Port | Storage |
|---------|-------|------|---------|
| gotosocial | `superseriousbusiness/gotosocial:0.17.3` | 127.0.0.1:8081 | `./gotosocial_data/` |

### Data Storage

All GoToSocial data lives in `gotosocial_data/`:
- `sqlite.db` - Database (accounts, posts, follows)
- Media files (avatars, attachments)

---

## Configuration

GoToSocial is configured via environment variables in `docker-compose.yml`:

| Variable | Value | Description |
|----------|-------|-------------|
| `GTS_HOST` | `${GOTOSOCIAL_DOMAIN}` | Your social domain |
| `GTS_DB_TYPE` | `sqlite` | Database type |
| `GTS_DB_ADDRESS` | `/gotosocial/storage/sqlite.db` | Database path |
| `GTS_LETSENCRYPT_ENABLED` | `false` | SSL handled by nginx |
| `GTS_TRUSTED_PROXIES` | `172.17.0.0/16,127.0.0.1` | Docker network |

For advanced configuration, see [GoToSocial Configuration Docs](https://docs.gotosocial.org/en/latest/configuration/).

---

## Backup & Restore

### Backup

GoToSocial data is stored in `gotosocial_data/`. Back it up with:

```bash
# On server
tar -czf gotosocial_backup_$(date +%Y%m%d).tar.gz gotosocial_data/
```

### Restore

```bash
# Stop container
docker compose --profile gotosocial stop gotosocial

# Restore data
rm -rf gotosocial_data/
tar -xzf gotosocial_backup_20241216.tar.gz

# Start container
docker compose --profile gotosocial up -d gotosocial
```

---

## Troubleshooting

### Container Not Running

```bash
# Check if container exists
docker ps -a | grep gotosocial

# Check logs
docker logs stormcloud_gotosocial

# Verify profile is enabled
docker compose --profile gotosocial ps
```

### Federation Not Working

1. **Check DNS** - Verify `social.example.com` resolves to your server
2. **Check SSL** - Visit `https://social.example.com` in browser
3. **Check WebFinger** - `curl https://social.example.com/.well-known/webfinger?resource=acct:yourname@social.example.com`

### Can't Login from App

1. Verify you created and confirmed user with `make gotosocial-user`
2. Check password is correct
3. Try web login at `https://social.example.com/auth/sign_in`

### Media Not Loading

Check nginx logs:
```bash
sudo tail -f /var/log/nginx/gotosocial.error.log
```

Verify media directory permissions:
```bash
ls -la gotosocial_data/
```

---

## Disabling GoToSocial

To remove GoToSocial from your deployment:

### 1. Update Config

Edit `deploy/config.yml`:
```yaml
install_gotosocial: false
```

### 2. Redeploy

```bash
make deploy
```

### 3. Clean Up (Optional)

Remove container and data:
```bash
docker rm -f stormcloud_gotosocial
rm -rf gotosocial_data/  # WARNING: Deletes all posts and media
```

Remove nginx config (on server):
```bash
sudo rm /etc/nginx/sites-enabled/gotosocial
sudo rm /etc/nginx/sites-available/gotosocial
sudo nginx -t && sudo systemctl reload nginx
```

---

## Related Documentation

- [GoToSocial Official Docs](https://docs.gotosocial.org/)
- [Setup Guide](../setup.md) - Storm Cloud installation
- [Production Monitoring](../production/monitoring.md) - Error tracking

---

## Getting Help

- **GoToSocial Issues:** [GitHub](https://github.com/superseriousbusiness/gotosocial/issues)
- **Storm Cloud Issues:** [GitHub](https://github.com/smattymatty/storm-cloud-server/issues)
- **Fediverse:** Ask on Mastodon with `#GoToSocial` hashtag
