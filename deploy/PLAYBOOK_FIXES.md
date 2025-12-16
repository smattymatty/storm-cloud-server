# Ansible Playbook Fixes - Storm Cloud Server

**Date:** 2025-12-16  
**Status:** ✅ Fixed  
**Version:** 2.0 (Git Recovery Edition)

---

## 🐛 Issues Fixed

### **Critical Issue #0: Git Recovery Logic (NEW)**
**Location:** Lines 504-592  
**Symptom:** Deployment fails when directory exists but `.git` is missing

**Root Cause:**
- Previous logic deleted entire directory (losing `.env`, `uploads/`, `gotosocial_data/`)
- Users would lose configuration and data on re-deployment after failed state
- No way to recover from partial deployments gracefully

**Fix:**
Replaced "nuke and clone" strategy with intelligent git recovery:

```yaml
# Step 1: Fix ownership if directory is owned by root
- name: Fix directory ownership (if owned by root)
  ansible.builtin.file:
    path: "{{ install_path }}"
    owner: "{{ app_user }}"
    recurse: true
  become: true
  when:
    - install_dir.stat.exists
    - git_dir does not exist
    - install_dir.stat.pw_name == 'root'

# Step 2: Initialize git in existing directory
- name: Initialize git repository (recovery mode)
  command: git init
  become_user: "{{ app_user }}"
  when: directory exists but no .git

# Step 3: Add/update remote origin
- name: Add remote origin (recovery mode)
  command: git remote add origin <repo_url>
  failed_when: false  # Ignore if exists

- name: Set remote URL (if remote already existed)
  command: git remote set-url origin <repo_url>
  when: previous task failed

# Step 4: Fetch and hard reset to target branch
- name: Fetch from remote (recovery mode)
  command: git fetch origin <branch>

- name: Hard reset to target branch (recovery mode)
  command: git reset --hard origin/<branch>

# Step 5: Set git_result for downstream tasks
- name: Set git_result for recovery path
  set_fact:
    git_result:
      changed: true
      failed: false
```

**Benefits:**
- ✅ Preserves `.env` (secrets, database passwords)
- ✅ Preserves `uploads/` (user files)
- ✅ Preserves `gotosocial_data/` (Fediverse database, media)
- ✅ Fixes ownership issues automatically
- ✅ Idempotent — can run multiple times safely
- ✅ Normal clone/update paths unaffected

---

### **Critical Issue #1: Permission Escalation Bug**
**Location:** Lines 490-509  
**Symptom:** Deployment fails on second run with "directory already exists and is not empty"

**Root Cause:**
- Playbook runs with `become: true` at play level
- Git clone task runs as `stormcloud` user (`become_user: stormcloud`)
- Cleanup tasks ran without `become: true`, causing permission denied on root-owned directories
- `stat` module couldn't check ownership, leading to incorrect cleanup logic

**Fix:**
```yaml
- name: Check if git repo exists
  ansible.builtin.stat:
    path: "{{ install_path }}/.git"
  become: true  # ← ADDED
  register: git_dir

- name: Check if install directory exists
  ansible.builtin.stat:
    path: "{{ install_path }}"
  become: true  # ← ADDED
  register: install_dir

- name: Remove invalid directory
  ansible.builtin.file:
    path: "{{ install_path }}"
    state: absent
  become: true  # ← ADDED
  when:
    - install_dir.stat.exists
    - git_dir.stat.exists is not defined or not git_dir.stat.exists
```

---

### **Critical Issue #2: Directory Creation Race Condition**
**Location:** Lines 521-537  
**Symptom:** `gotosocial_data/` directory created as `root:root` even when git clone fails

**Root Cause:**
- Directory creation tasks ran unconditionally
- If git clone failed, parent directory (`/home/stormcloud/storm-cloud-server/`) was created by file module
- Created with `root:root` ownership due to play-level `become: true`
- Subsequent deployments couldn't clean up root-owned directory

**Fix:**
```yaml
- name: Create directories
  ansible.builtin.file:
    path: "{{ install_path }}/{{ item }}"
    state: directory
    owner: "{{ app_user }}"
    mode: "0750"  # ← CHANGED from 0755 (bonus security fix)
  loop: [uploads, backups]
  when: git_result is succeeded  # ← ADDED: Only create if git clone succeeded

- name: Create GoToSocial data directory
  ansible.builtin.file:
    path: "{{ install_path }}/gotosocial_data"
    state: directory
    owner: "{{ app_user }}"
    mode: "0755"
  when:
    - install_gotosocial | default(false)
    - git_result is succeeded  # ← ADDED: Only create if git clone succeeded
```

---

### **Critical Issue #3: Unsafe Secret Parsing**
**Location:** Lines 565-570  
**Symptom:** Playbook crashes if secrets are malformed or missing from `.env`

**Root Cause:**
- Regex `(.+)$` captured everything to end of line (including comments, whitespace)
- `.first` filter crashed on empty list if regex didn't match
- No validation that parsed secrets were non-empty

**Fix:**
```yaml
- name: Parse existing secrets
  ansible.builtin.set_fact:
    # ↓ CHANGED: Stop at whitespace/comments, provide default empty list
    secret_key: "{{ env_content.content | b64decode | regex_search('SECRET_KEY=([^\\s#]+)', '\\1', multiline=True) | default([''], true) | first }}"
    db_password: "{{ env_content.content | b64decode | regex_search('POSTGRES_PASSWORD=([^\\s#]+)', '\\1', multiline=True) | default([''], true) | first }}"
  when: env_check.stat.exists

# ↓ ADDED: Validate parsed secrets
- name: Validate parsed secrets
  ansible.builtin.assert:
    that:
      - secret_key | default('') | length > 0
      - db_password | default('') | length > 0
    fail_msg: |
      ══════════════════════════════════════════════════════════════
      ❌ Failed to parse secrets from existing .env file
      ══════════════════════════════════════════════════════════════
      
      The existing .env file appears to be corrupted or missing
      required SECRET_KEY and POSTGRES_PASSWORD values.
      
      Please either:
      1. Fix the .env file manually on the server
      2. Remove the .env file to generate new secrets (WARNING: breaks existing data)
      
      ══════════════════════════════════════════════════════════════
  when: env_check.stat.exists
```

---

### **Security Fix #4: Prevent Secret Exposure**
**Location:** Line 572  
**Symptom:** Secrets visible in Ansible logs when run with `-vv` or `--diff`

**Fix:**
```yaml
- name: Write .env
  ansible.builtin.template:
    src: templates/dotenv.j2
    dest: "{{ install_path }}/.env"
    owner: "{{ app_user }}"
    mode: "0600"
  no_log: true  # ← ADDED: Prevent secrets from appearing in logs
```

---

### **Security Fix #5: Tighter Directory Permissions**
**Location:** Line 527  
**Symptom:** Uploads directory world-readable (`0755`)

**Fix:**
```yaml
mode: "0750"  # ← CHANGED from 0755 (owner + group read, no world access)
```

---

## 🛠️ Manual Cleanup Required (First Deployment Only)

If you've already attempted deployment and have a broken directory, run this on the **remote server**:

```bash
# Option 1: Use the cleanup script (recommended)
sudo bash /home/stormcloud/storm-cloud-server/deploy/cleanup-failed-deployment.sh

# Option 2: Manual removal
sudo rm -rf /home/stormcloud/storm-cloud-server
```

Then from your **local machine**:

```bash
make deploy
```

The fixed playbook will now correctly handle the deployment.

---

## ✅ Testing

After applying these fixes, the playbook handles all deployment scenarios:

### **Scenario 1: Fresh Deployment**
```bash
# Server state: No directory exists
make deploy
# Expected: Normal git clone → creates directory → success
```

### **Scenario 2: Re-deployment (Normal Update)**
```bash
# Server state: Valid git repo exists
make deploy
# Expected: Git pull/update → success
```

### **Scenario 3: Git Recovery - Empty Broken Directory**
```bash
# On remote server:
sudo mkdir /home/stormcloud/storm-cloud-server
sudo mkdir /home/stormcloud/storm-cloud-server/gotosocial_data

# From local machine:
make deploy
# Expected: Fix ownership → git init → fetch → reset → success
# Result: gotosocial_data/ preserved
```

### **Scenario 4: Git Recovery - Directory with .env**
```bash
# On remote server:
sudo mkdir -p /home/stormcloud/storm-cloud-server
echo "SECRET_KEY=test123" | sudo tee /home/stormcloud/storm-cloud-server/.env

# From local machine:
make deploy
# Expected: Fix ownership → git init → fetch → reset → success
# Result: .env preserved, secrets intact
```

### **Scenario 5: Root-Owned Directory Recovery**
```bash
# On remote server (simulate failed deployment):
sudo mkdir -p /home/stormcloud/storm-cloud-server/uploads
sudo touch /home/stormcloud/storm-cloud-server/.env
# Directory now owned by root:root

# From local machine:
make deploy
# Expected: Fix ownership → git init → fetch → reset → success
# Result: Ownership changed to stormcloud:stormcloud
```

---

## 📊 Changes Summary

| Issue | Severity | Status | Lines Changed |
|-------|----------|--------|---------------|
| **Git recovery logic** | **Critical** | ✅ **Fixed** | **89 additions (lines 504-592)** |
| Permission escalation bug | Critical | ✅ Fixed | 3 additions (lines 493, 500, 508) |
| Directory creation race | Critical | ✅ Fixed | 2 additions (lines 631, 642-643) |
| Secret parsing crash | Critical | ✅ Fixed | 2 changes + 22 additions (lines 673, 676, 678-699) |
| Secret log exposure | High | ✅ Fixed | 1 addition (line 706) |
| Directory permissions | Medium | ✅ Fixed | 1 change (line 629) |

**Total:** 120 lines changed/added

**New Capabilities:**
- ✅ Automatic git recovery from broken deployments
- ✅ Preserves user data (.env, uploads/, gotosocial_data/)
- ✅ Fixes ownership issues automatically
- ✅ Idempotent recovery process

---

## 🔮 Future Improvements (Not Blocking)

1. **Add rollback logic** for failed container builds
2. **Add cert renewal task** (currently relies on system cron)
3. **Use `docker compose exec`** instead of hardcoded container names
4. **Add post-deployment smoke tests** (verify endpoints respond)

---

## 📝 Notes

- All fixes are **backward-compatible** with existing deployments
- No changes to `docker-compose.yml` or templates required
- Cleanup script (`deploy/cleanup-failed-deployment.sh`) is idempotent and safe to re-run

---

**Questions?** Open an issue at https://github.com/smattymatty/storm-cloud-server/issues
