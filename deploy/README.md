# Storm Cloud Server - Deployment

Automated deployment using Ansible.

## Quick Start

```bash
# 1. Install Ansible (on your local machine)
pip install ansible

# 2. Copy and edit config
cp config.example.yml config.yml
nano config.yml

# 3. Deploy
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

## File Structure

```
deploy/
├── config.example.yml      # Template - copy to config.yml
├── config.yml              # Your config (git-ignored)
├── README.md               # This file
│
└── ansible/
    ├── inventory.yml       # Host definition
    ├── playbook.yml        # Main deployment playbook
    ├── requirements.yml    # Galaxy dependencies
    │
    └── templates/
        ├── nginx-stormcloud.conf.j2   # nginx config
        └── dotenv.j2                   # .env file
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