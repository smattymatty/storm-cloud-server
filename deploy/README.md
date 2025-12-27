# Storm Cloud Server - Deployment

Automated deployment using Ansible.

## Quick Start

```bash
# 1. Install Ansible (on your local machine)
pip install ansible

# 2. Copy and edit config
cp deploy/config.example.yml deploy/config.yml
nano deploy/config.yml  # Set server_ip, domain, admin_email

# 3. Set secrets as environment variables
export STORMCLOUD_POSTGRES_PASSWORD="your-secure-password"
# SECRET_KEY is optional - will auto-generate if not set

# 4. Deploy
make deploy
```

That's it. Your Storm Cloud Server will be live at `https://your-domain.ca`.

## What You Need

1. **A VPS** - Any provider (DigitalOcean, Linode, Hetzner, StormWeb, etc.)
   - Ubuntu 22.04 or 24.04
   - Minimum: 1 CPU, 1GB RAM, 10GB disk
   - Root SSH access

2. **A domain** - Pointed to your VPS IP via DNS A record

3. **Ansible** - Installed on your local machine (`pip install ansible`)

## Configuration

Edit `config.yml` with your values:

```yaml
# REQUIRED
server_ip: "123.45.67.89"           # Your VPS IP
domain: "cloud.example.com"          # Your domain
admin_email: "you@example.com"       # For SSL notifications

# OPTIONAL (defaults are fine)
ssh_user: root
app_user: stormcloud
web_port: 8000
```

## Secrets

Secrets are managed via environment variables (not stored in `config.yml` for better security).

### Required Secrets

**PostgreSQL Password** - Required for database access

```bash
export STORMCLOUD_POSTGRES_PASSWORD="your-secure-password"
```

Generate a strong password:
```bash
openssl rand -base64 32
```

**Django SECRET_KEY** - Optional (will auto-generate if not provided)

```bash
export STORMCLOUD_SECRET_KEY="your-django-secret-key"
```

If not set, a random 50-character key will be auto-generated and displayed during deployment. **Save this key** for future deployments.

### Optional Secrets (GoToSocial)

If deploying with GoToSocial enabled (`install_gotosocial: true`):

```bash
export STORMCLOUD_GOTOSOCIAL_USERNAME="your-username"
export STORMCLOUD_GOTOSOCIAL_EMAIL="you@example.com"
export STORMCLOUD_GOTOSOCIAL_PASSWORD="your-secure-password"  # Min 16 chars
```

### Copy-Paste Template

```bash
# Required
export STORMCLOUD_POSTGRES_PASSWORD="CHANGE_ME"

# Optional (will prompt if not set)
export STORMCLOUD_SECRET_KEY=""  # Auto-generates if empty
export STORMCLOUD_GOTOSOCIAL_USERNAME=""
export STORMCLOUD_GOTOSOCIAL_EMAIL=""
export STORMCLOUD_GOTOSOCIAL_PASSWORD=""

# Deploy
make deploy
```

### Password Manager Integration

Use your password manager's CLI to inject secrets:

**1Password:**
```bash
export STORMCLOUD_POSTGRES_PASSWORD=$(op read "op://vault/stormcloud/postgres_password")
make deploy
```

**Bitwarden:**
```bash
export STORMCLOUD_POSTGRES_PASSWORD=$(bw get password postgres_stormcloud)
make deploy
```

**Pass (Unix password manager):**
```bash
export STORMCLOUD_POSTGRES_PASSWORD=$(pass show stormcloud/postgres_password)
make deploy
```

### Interactive Prompts

If environment variables are not set, you'll be prompted during deployment:

```
PostgreSQL password (or set STORMCLOUD_POSTGRES_PASSWORD env var): ********
Django SECRET_KEY (press ENTER to auto-generate): [ENTER]
```

This is convenient for one-off deployments but less suitable for automation/CI-CD.

## Commands

From the project root:

```bash
make deploy          # Full deployment
make deploy-check    # Dry run (shows what would change)
make deploy-app      # Update application only (skip system setup)
make deploy-nginx    # Update nginx config only
```

## What Gets Installed

The playbook installs and configures:

- **Docker** + Docker Compose
- **nginx** - Reverse proxy with SSL
- **Certbot** - Let's Encrypt SSL certificates
- **UFW** - Firewall (allows SSH, HTTP, HTTPS only)
- **Storm Cloud Server** - The application itself

## After Deployment

SSH into your server and create an admin account:

```bash
ssh root@your-server-ip
su - stormcloud
cd storm-cloud-server
make superuser
make api_key
```

Save the API key - you'll need it to connect from the CLI or web UI.

## Updating

To update to the latest version:

```bash
# From your local machine
make deploy-app

# Or SSH in and update manually
ssh root@your-server-ip
su - stormcloud
cd storm-cloud-server
git pull
make up
```

## Troubleshooting

### "Connection refused" or timeout

- Verify `server_ip` is correct in config.yml
- Ensure you can SSH manually: `ssh root@your-server-ip`
- Check if firewall is blocking (some providers have external firewalls)

### SSL certificate fails

- Verify DNS A record points to your server IP: `dig +short your-domain.com`
- DNS propagation can take up to 48 hours (usually 5-30 minutes)
- Check certbot logs: `sudo cat /var/log/letsencrypt/letsencrypt.log`

### Application not starting

SSH in and check Docker:

```bash
su - stormcloud
cd storm-cloud-server
docker compose ps        # Check container status
docker compose logs      # Check logs
make logs               # Interactive log viewer
```

### nginx errors

```bash
sudo nginx -t                    # Test configuration
sudo tail -f /var/log/nginx/stormcloud.error.log  # View errors
```

## Destruction 💀

**⚠️ WARNING: These commands will PERMANENTLY DELETE your deployment!**

### Safe Destruction (Interactive)

Preview what will be destroyed (dry-run):
```bash
make destroy-check
```

Full destruction with confirmations:
```bash
make destroy
```

**You will be prompted to:**
1. Confirm server IP address
2. Type 'DESTROY' in all caps
3. Choose whether to create a backup first
4. Wait 10 seconds (final abort chance)

**What gets deleted:**
- All Docker containers, images, volumes
- Application directory (`/home/stormcloud/storm-cloud-server/`)
- All uploaded files and database data
- nginx configuration files
- SSL certificates
- Application user account
- Docker, nginx, and certbot packages
- All logs and traces

### Selective Destruction

Application only (keep system packages):
```bash
make destroy-app
```

**Deletes:** Containers, app directory, uploads, database  
**Keeps:** Docker, nginx, certbot (installed and configured)

### Emergency Destruction (Skip Confirmations)

**⚠️ USE WITH EXTREME CAUTION - NO CONFIRMATIONS!**

```bash
make destroy-force
# 5 second countdown, then TOTAL ANNIHILATION
```

This is for automation/CI or when you're absolutely sure.

### Backup Before Destruction

The playbook will prompt you to create a final backup. To automate this:

```bash
# Create backup manually first
ssh root@your-server-ip
su - stormcloud
cd storm-cloud-server
./scripts/backup.sh

# Then destroy
make destroy
```

### After Destruction

Your VPS will be returned to a clean state (all Storm Cloud packages removed).

To redeploy:
```bash
make deploy
```

### When to Use Destroy

**Testing/Development:**
- Testing deployment scripts
- Iterating on infrastructure changes
- Clean slate for new configuration

**Production:**
- Migrating to new server
- Complete platform change
- Emergency security incident response
- Permanent shutdown

**Before destroying production:**
1. ✅ Create and verify backups
2. ✅ Download any critical files
3. ✅ Export database if needed
4. ✅ Revoke API keys
5. ✅ Update DNS if migrating

## File Structure

```
deploy/
├── config.example.yml      # Template - copy to config.yml
├── config.yml              # Your config (git-ignored)
├── README.md               # This file
├── SECRETS_MIGRATION.md    # Secret management documentation
│
└── ansible/
    ├── inventory.yml       # Host definition
    ├── playbook.yml        # Main deployment playbook
    ├── destroy.yml         # 💀 Destruction playbook
    ├── requirements.yml    # Galaxy dependencies
    │
    ├── library/
    │   └── read_dotenv.py  # Custom .env parser module
    │
    ├── templates/
    │   ├── nginx-stormcloud.conf.j2   # nginx config
    │   └── dotenv.j2                   # .env file
    │
    └── tests/
        ├── test_dotenv_parser.py       # Unit tests
        └── test_playbook.yml           # Integration tests
```

## Advanced Usage

### Run specific parts only

```bash
# Only firewall tasks
cd deploy/ansible
ansible-playbook playbook.yml -i inventory.yml --extra-vars "@../config.yml" --tags firewall

# Only nginx tasks
ansible-playbook playbook.yml -i inventory.yml --extra-vars "@../config.yml" --tags nginx

# Only application deployment
ansible-playbook playbook.yml -i inventory.yml --extra-vars "@../config.yml" --tags app
```

### Multiple servers

Create separate config files:

```bash
cp config.example.yml config-prod.yml
cp config.example.yml config-staging.yml
```

Deploy to specific environment:

```bash
cd deploy/ansible
ansible-playbook playbook.yml -i inventory.yml --extra-vars "@../config-prod.yml"
```

### Custom variables

Override any variable at deploy time:

```bash
make deploy EXTRA_VARS="git_branch=develop web_port=8080"
```