# Secrets Management Migration

**Date:** December 2024  
**Status:** ✅ Implemented  
**Security Level:** 6/10 (mid-tier - environment variables + secure storage)

## Summary

Migrated secret management from plaintext `config.yml` to environment variables with optional password manager integration. This improves security by keeping secrets out of configuration files and enables better secret rotation workflows.

## What Changed

### Before (Plaintext Config)

```yaml
# deploy/config.yml
postgres_password: "MySecureP@ssw0rd!2024"  # ❌ Plaintext on laptop
```

Secrets stored in `config.yml` → templated into server `.env` file.

**Problems:**
- Secrets in plaintext on developer machine
- Secrets in git if accidentally committed
- No secret rotation strategy
- Hard to integrate with password managers

### After (Environment Variables)

```bash
export STORMCLOUD_POSTGRES_PASSWORD="MySecureP@ssw0rd!2024"
export STORMCLOUD_SECRET_KEY="django-secret-key"  # Optional (auto-generates)
make deploy
```

Secrets from env vars → templated into server `.env` file. Falls back to interactive prompts if not set.

**Benefits:**
- ✅ No plaintext secrets in config files
- ✅ Works with password manager CLIs (1Password, Bitwarden, Pass)
- ✅ CI/CD friendly (use GitHub/GitLab secrets)
- ✅ Interactive prompt fallback for manual deployments
- ✅ Auto-generation for SECRET_KEY

## New Secret Management System

### Supported Secrets

| Secret | Environment Variable | Required | Default Behavior |
|--------|---------------------|----------|------------------|
| PostgreSQL Password | `STORMCLOUD_POSTGRES_PASSWORD` | ✅ Yes | Prompts if not set |
| Django SECRET_KEY | `STORMCLOUD_SECRET_KEY` | ❌ No | Auto-generates if not set |

### Resolution Order

1. **Environment variable** (highest priority)
2. **Interactive prompt** (fallback)
3. **Auto-generation** (SECRET_KEY only)
4. **Existing .env on server** (preserved across deployments)

### Usage Examples

**Basic (Interactive):**
```bash
make deploy
# Prompts:
# PostgreSQL password: ********
# Django SECRET_KEY (press ENTER to auto-generate): [ENTER]
```

**Environment Variables:**
```bash
export STORMCLOUD_POSTGRES_PASSWORD="your-password"
make deploy  # No prompts
```

**Password Manager (1Password):**
```bash
export STORMCLOUD_POSTGRES_PASSWORD=$(op read "op://vault/stormcloud/postgres_password")
make deploy
```

**Password Manager (Bitwarden):**
```bash
export STORMCLOUD_POSTGRES_PASSWORD=$(bw get password postgres_stormcloud)
make deploy
```

**CI/CD (GitHub Actions):**
```yaml
- name: Deploy
  env:
    STORMCLOUD_POSTGRES_PASSWORD: ${{ secrets.POSTGRES_PASSWORD }}
    STORMCLOUD_SECRET_KEY: ${{ secrets.SECRET_KEY }}
  run: make deploy
```

## Technical Implementation

### 1. Custom Ansible Module (`read_dotenv.py`)

Replaces fragile regex parsing with proper `.env` file parser.

**Features:**
- Handles quoted values (single/double quotes)
- Multiline value support
- Comments (inline and full-line)
- Special characters
- Equals signs in values
- Whitespace tolerance

**Location:** `deploy/ansible/library/read_dotenv.py`  
**Tests:** `deploy/ansible/tests/test_dotenv_parser.py` (19 test cases, all passing)

### 2. Playbook Updates

**Secret Resolution (Hybrid Approach):**
```yaml
- name: Resolve secrets (env vars take precedence over prompts)
  ansible.builtin.set_fact:
    postgres_password: "{{ lookup('env', 'STORMCLOUD_POSTGRES_PASSWORD') | default(_postgres_password_prompt, true) }}"
    secret_key_input: "{{ lookup('env', 'STORMCLOUD_SECRET_KEY') | default(_secret_key_prompt, true) }}"
  no_log: true
```

**Auto-Generation:**
```yaml
- name: Auto-generate SECRET_KEY if not provided
  ansible.builtin.set_fact:
    secret_key_generated: "{{ lookup('password', '/dev/null length=50 chars=ascii_letters,digits,punctuation') }}"
  when: secret_key_input | default('') | length == 0
```

**Secret Preservation:**
```yaml
- name: Read existing secrets from .env
  read_dotenv:
    path: "{{ install_path }}/.env"
    keys: [SECRET_KEY, POSTGRES_PASSWORD]
  when: env_check.stat.exists

- name: Preserve existing secrets
  ansible.builtin.set_fact:
    secret_key: "{{ existing_secrets.values.SECRET_KEY }}"
  when: existing_secrets.values.SECRET_KEY is defined
```

### 3. Validation & Error Messages

**Helpful errors when secrets missing:**
```
══════════════════════════════════════════════════════════════
❌ STORMCLOUD_POSTGRES_PASSWORD is required
══════════════════════════════════════════════════════════════

Set secrets as environment variables before deploying:

  export STORMCLOUD_POSTGRES_PASSWORD="your-secure-password"
  export STORMCLOUD_SECRET_KEY="your-django-secret-key"

Generate a secure password:
  openssl rand -base64 32

Need help? See: deploy/README.md#secrets
══════════════════════════════════════════════════════════════
```

### 4. Makefile Integration

Pre-flight check shows secret status:
```bash
Checking secrets...
⚠️  STORMCLOUD_POSTGRES_PASSWORD not set
   You will be prompted during deployment.

Tip: Set secrets beforehand for non-interactive deployment:
  export STORMCLOUD_POSTGRES_PASSWORD="your-password"
```

## Migration Path

### For Existing Deployments

**No action required.** Existing secrets in server `.env` files are automatically preserved.

**Optional:** Migrate to env var workflow:
```bash
# Extract current password from config.yml
OLD_PASSWORD=$(grep postgres_password deploy/config.yml | cut -d'"' -f2)

# Set as env var
export STORMCLOUD_POSTGRES_PASSWORD="$OLD_PASSWORD"

# Remove from config.yml
# (Already done - config.example.yml updated)

# Deploy normally
make deploy
```

### For New Deployments

1. Set required env vars before deploying
2. Or rely on interactive prompts
3. Save auto-generated SECRET_KEY if shown

## Security Improvements

| Attack Vector | Before | After |
|--------------|--------|-------|
| **Laptop compromise** | ❌ Secrets exposed in `config.yml` | ✅ Secrets in env vars (transient) |
| **Accidental git commit** | ❌ Secrets could be committed | ✅ Config file has no secrets |
| **Secret rotation** | ❌ No documented process | ✅ Set new env var, redeploy |
| **Multiple maintainers** | ❌ Everyone needs config.yml | ✅ Each uses their own method |
| **CI/CD** | ❌ Hardcode or manual intervention | ✅ Use platform secrets |
| **Password manager** | ❌ Manual copy-paste | ✅ CLI integration |

## Testing

### Unit Tests (DotenvParser)

```bash
cd deploy/ansible/tests
python3 test_dotenv_parser.py

# Output:
# Ran 19 tests in 0.002s
# OK
```

### Integration Tests (Ansible Module)

```bash
cd deploy/ansible
ansible-playbook tests/test_playbook.yml

# Output:
# ✓ All read_dotenv module tests passed!
```

## Documentation

- **User Guide:** `deploy/README.md#secrets` - Full workflow documentation
- **Config Template:** `deploy/config.example.yml` - Updated with env var instructions
- **Test README:** `deploy/ansible/tests/README.md` - How to run/add tests
- **This Document:** `deploy/SECRETS_MIGRATION.md` - Technical details

## Future Improvements

### Next Steps (Priority 2)

1. **Secret rotation playbook** - Automated password rotation
   ```bash
   make rotate-db-password
   make rotate-django-secret
   ```

2. **Backup encryption** - Encrypt backups with separate key
   ```bash
   export STORMCLOUD_BACKUP_KEY="backup-encryption-key"
   ```

3. **Audit logging** - Track who deployed when with which secrets
   ```bash
   # Log deployments to centralized system
   ```

### Long-term (Priority 3)

1. **HashiCorp Vault integration** - Enterprise secret management
2. **AWS Secrets Manager** - Cloud-native secrets
3. **Automated secret expiration** - Force rotation every 90 days

## Questions?

See `deploy/README.md#secrets` for usage examples or open an issue.
