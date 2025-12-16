# Git Recovery Guide - Storm Cloud Server

**Version:** 2.0  
**Date:** 2025-12-16

---

## 🎯 What This Solves

Previously, if your deployment failed mid-way, you'd be stuck with a broken directory that couldn't be cleaned up without losing data. The playbook would:

❌ **Old Behavior:**
```
Broken deployment → delete entire directory → lose .env, uploads/, gotosocial_data/
```

✅ **New Behavior:**
```
Broken deployment → detect broken state → initialize git in-place → preserve all data
```

---

## 🔍 How Git Recovery Works

The playbook now has **three deployment paths**:

### **Path 1: Fresh Deployment** (no directory exists)
```
Check directory → doesn't exist → git clone → success
```

### **Path 2: Normal Update** (valid git repo exists)
```
Check directory → exists with .git → git pull/update → success
```

### **Path 3: Git Recovery** ⭐ NEW
```
Check directory → exists WITHOUT .git
  ↓
Fix ownership (if root-owned)
  ↓
git init
  ↓
git remote add origin <repo_url>
  ↓
git fetch origin main
  ↓
git reset --hard origin/main
  ↓
Success (with data preserved)
```

---

## 📋 What Gets Preserved

During git recovery, these files/directories are **never deleted**:

- ✅ `.env` (secrets, database passwords)
- ✅ `uploads/` (user-uploaded files)
- ✅ `backups/` (backup files)
- ✅ `gotosocial_data/` (Fediverse database, media, accounts)
- ✅ Any other non-tracked files

Git's `reset --hard` only affects **tracked files** (code, configs, templates). Your data is safe.

---

## 🛠️ Manual Recovery (Optional)

If you want to manually trigger git recovery instead of waiting for deployment:

### **On the Remote Server:**

```bash
# SSH to server
ssh stormcloud

# Navigate to install directory
cd /home/stormcloud/storm-cloud-server

# Check current state
ls -la  # Should show gotosocial_data/, maybe .env, but no .git/

# Initialize git manually
git init
git remote add origin https://github.com/smattymatty/storm-cloud-server.git
git fetch origin main
git reset --hard origin/main

# Verify
ls -la .git  # Should now exist
git log -1   # Should show latest commit
```

Then run normal deployment:
```bash
# From local machine
make deploy
```

---

## 🧪 Testing the Recovery Path

### **Test 1: Simulate Broken Deployment**

```bash
# On remote server:
sudo rm -rf /home/stormcloud/storm-cloud-server/.git
sudo rm -rf /home/stormcloud/storm-cloud-server/README.md
# Directory now exists without .git

# From local machine:
make deploy
# Expected: Git recovery path activates, preserves gotosocial_data/
```

### **Test 2: Simulate Root-Owned Directory**

```bash
# On remote server:
sudo mkdir -p /home/stormcloud/storm-cloud-server/test
sudo chown root:root /home/stormcloud/storm-cloud-server
# Directory now owned by root

# From local machine:
make deploy
# Expected: Ownership fixed to stormcloud:stormcloud, then git recovery
```

### **Test 3: Recovery with Existing .env**

```bash
# On remote server:
echo "SECRET_KEY=preserve_this" > /home/stormcloud/storm-cloud-server/.env
sudo rm -rf /home/stormcloud/storm-cloud-server/.git

# From local machine:
make deploy
# Expected: Git recovery succeeds, .env preserved with original SECRET_KEY
```

---

## 🚨 When Git Recovery Runs

The recovery path **only** runs when:

1. Install directory exists (`/home/stormcloud/storm-cloud-server/`)
2. `.git` subdirectory does **not** exist
3. Normal clone would fail (directory not empty)

If directory doesn't exist → normal clone  
If `.git` exists → normal update  
If directory exists but no `.git` → **recovery**

---

## 📊 Recovery Path Tasks

Here's what happens during git recovery (in order):

| Task | Description | Runs As |
|------|-------------|---------|
| **Fix ownership** | Changes `root:root` to `stormcloud:stormcloud` | root (via `become`) |
| **git init** | Creates `.git` directory | stormcloud |
| **git remote add** | Adds origin URL | stormcloud |
| **git remote set-url** | Updates origin if already exists | stormcloud |
| **git fetch** | Downloads commits from remote | stormcloud |
| **git reset --hard** | Resets working tree to remote branch | stormcloud |
| **Set git_result** | Marks recovery as successful | - |

---

## ⚠️ Important Notes

### **What Git Reset Does**

`git reset --hard origin/main` will:
- ✅ Restore all tracked files to match remote
- ✅ Remove untracked files **that conflict** with tracked files
- ❌ **NOT** delete untracked files like `.env`, `uploads/`, `gotosocial_data/`

### **When NOT to Use Recovery**

If you've made **local code changes** you want to keep:
```bash
# On server, commit your changes first:
git add .
git commit -m "Local changes"
git push  # Or keep local-only

# Then recovery won't overwrite your commits
```

### **Rollback Strategy**

If recovery goes wrong:
```bash
# On server, check git reflog:
git reflog
# Find the commit before reset
git reset --hard HEAD@{1}  # Or specific SHA
```

---

## 🎓 Why This Approach?

**Why not just delete the directory?**

1. **Data Loss Prevention** - `.env` contains secrets that are hard to regenerate
2. **Faster Recovery** - No need to re-configure GoToSocial, re-upload files
3. **Idempotent** - Can run multiple times without side effects
4. **Production-Safe** - Works on live servers without downtime

**Why `reset --hard` instead of `pull`?**

1. `git pull` requires existing commits (we just did `git init`)
2. `reset --hard` works from any state (clean or dirty)
3. Guarantees working tree matches remote exactly

---

## 🔧 Troubleshooting

### **Problem: "fatal: couldn't find remote ref main"**

**Cause:** Branch name mismatch (using `master` instead of `main`)

**Fix:**
```yaml
# In config.yml or inventory:
git_branch: master  # Or whatever your default branch is
```

### **Problem: "Permission denied" during git init**

**Cause:** Directory still owned by root

**Fix:** Run ownership fix task manually:
```bash
sudo chown -R stormcloud:stormcloud /home/stormcloud/storm-cloud-server
```

### **Problem: Git recovery runs but files are missing**

**Cause:** Files were tracked by git and got overwritten

**Fix:** Move data to untracked location:
```bash
# Before deployment:
ssh stormcloud
mv uploads uploads.backup
# After deployment:
mv uploads.backup uploads
```

---

## 📚 Related Documentation

- [PLAYBOOK_FIXES.md](./PLAYBOOK_FIXES.md) - Full list of playbook fixes
- [cleanup-failed-deployment.sh](./cleanup-failed-deployment.sh) - Manual cleanup script (legacy)
- [../README.md](../README.md) - Main project documentation

---

## ✅ Quick Reference

```bash
# Scenario 1: Fresh deployment
make deploy  # Just works

# Scenario 2: Update existing deployment
make deploy  # Just works

# Scenario 3: Broken deployment (no .git)
make deploy  # Git recovery auto-runs

# Scenario 4: Manual recovery needed
ssh stormcloud
cd /home/stormcloud/storm-cloud-server
git init
git remote add origin https://github.com/smattymatty/storm-cloud-server.git
git fetch origin main
git reset --hard origin/main
exit
make deploy
```

---

**Questions?** Open an issue at https://github.com/smattymatty/storm-cloud-server/issues
