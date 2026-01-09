---
title: Server-Side Encryption
published: 2026-01-08
modified: 2026-01-08
tags:
  - storage
  - encryption
  - security
---

Protect files at rest with AES-256-GCM encryption. Files are encrypted before writing to disk and transparently decrypted on download.

---

## Overview

Storm Cloud supports server-side encryption at rest:

- **AES-256-GCM** - Industry-standard authenticated encryption
- **Transparent** - Upload and download work normally, encryption is automatic
- **Mixed-mode** - Handles plaintext files uploaded before encryption was enabled
- **29 bytes overhead** - Minimal storage cost per file

---

## Enabling Encryption

### 1. Generate Encryption Key

Generate a secure 256-bit key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Output example:
```
K7xPq2mN8vR3tY6wZ9aB4cD5eF0gH1iJ2kL3mN4oP5s=
```

**Save this key securely!** Store it in your password manager or secrets vault.

### 2. Set Environment Variable

Before deploying, export the key:

```bash
export STORMCLOUD_ENCRYPTION_KEY="K7xPq2mN8vR3tY6wZ9aB4cD5eF0gH1iJ2kL3mN4oP5s="
```

### 3. Deploy

```bash
make deploy
```

The deployment will:
- Detect the encryption key automatically
- Enable server-side encryption
- Show a warning to save your key (first time only)

---

## Encrypting Existing Files

If you enable encryption on a server with existing unencrypted files, use the migration commands:

### Audit Mode

See how many files need encryption (no changes made):

```bash
make encrypt-audit
```

Output shows:
- Files already encrypted
- Files needing encryption
- Files with issues

### Encrypt Mode

Encrypt all unencrypted files:

```bash
make encrypt-files
```

This will:
- Read each unencrypted file
- Encrypt and write it back
- Update database records
- Show progress

**Note:** For large file collections, this may take time. Files remain accessible during migration.

---

## Safety Features

Storm Cloud prevents common encryption mistakes:

### Key Mismatch Detection

If the server has encrypted files but you deploy with a different key:

```
FATAL: Encryption key mismatch detected!
Server has encrypted files with a different key.
Deployment blocked to prevent data loss.
```

**Resolution:** Use the original key or restore from backup.

### Cannot Disable Encryption

If the server has encryption enabled but you deploy without a key:

```
FATAL: Server has encryption enabled, but no key provided.
Cannot disable encryption - this would make files unreadable.
```

**Resolution:** Always provide `STORMCLOUD_ENCRYPTION_KEY` for encrypted servers.

### First-Time Warning

When enabling encryption for the first time:

```
NOTICE: Server-side encryption being enabled for the first time.
SAVE YOUR ENCRYPTION KEY NOW:
  STORMCLOUD_ENCRYPTION_KEY=K7xPq2mN8vR3tY6...
Store this in your password manager. Losing this key = losing your files.
```

### Key Auto-Preservation

If you forget to set `STORMCLOUD_ENCRYPTION_KEY` but the server already has encryption configured, the existing key is preserved automatically.

---

## Technical Details

### Encryption Format

| Component | Size | Description |
|-----------|------|-------------|
| Version byte | 1 byte | `0x01` for AES-256-GCM |
| Nonce | 12 bytes | Random per file |
| Ciphertext | Variable | Encrypted file content |
| Auth tag | 16 bytes | GCM authentication tag |

**Total overhead:** 29 bytes per file

### Algorithm

- **Cipher:** AES-256-GCM (Galois/Counter Mode)
- **Key:** 256-bit (32 bytes), base64url-encoded
- **Nonce:** 12 bytes, cryptographically random per file
- **Authentication:** 16-byte GCM tag (integrity + authenticity)

### Mixed Mode

When encryption is enabled, the storage backend automatically handles both encrypted and plaintext files:

1. **Read file header** - Check for version byte `0x01`
2. **If encrypted** - Decrypt with configured key
3. **If plaintext** - Return as-is (legacy file)

This allows gradual migration without downtime.

---

## API Response

File metadata includes encryption status:

```json
{
  "path": "documents/report.pdf",
  "name": "report.pdf",
  "size": 1048576,
  "encrypted_size": 1048605,
  "encryption_method": "server",
  "content_type": "application/pdf"
}
```

| Field | Description |
|-------|-------------|
| `size` | Original file size (before encryption) |
| `encrypted_size` | Size on disk (with 29-byte overhead) |
| `encryption_method` | `"none"` or `"server"` |

---

## Troubleshooting

### DECRYPTION_FAILED Error

**Cause:** File cannot be decrypted (wrong key or corrupted file).

**Solutions:**
1. Verify `STORMCLOUD_ENCRYPTION_KEY` matches the key used to encrypt
2. Check if file was corrupted (restore from backup)
3. Run `make encrypt-audit` to identify affected files

### Key ID Tracking

Each file stores the `key_id` used to encrypt it:

```json
{
  "encryption_method": "server",
  "key_id": "1"
}
```

This prepares for future key rotation support.

### Audit Shows "File Not Found"

**Cause:** Database record exists but file missing from disk.

**Solution:** Run index rebuild to clean orphaned records:

```bash
python manage.py rebuild_index --mode clean --force
```

### Performance Considerations

- Encryption adds ~5% CPU overhead for uploads/downloads
- Files are encrypted in memory before writing
- Large files may temporarily use significant memory
- Consider chunked encryption for files >100MB (future enhancement)

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `STORMCLOUD_ENCRYPTION_KEY` | For encryption | (none) | Base64url-encoded 256-bit key |
| `STORMCLOUD_ENCRYPTION_KEY_ID` | No | `"1"` | Key identifier for rotation |

### Generate a Key

```bash
# Python
python -c "import secrets; print(secrets.token_urlsafe(32))"

# OpenSSL
openssl rand -base64 32 | tr '+/' '-_'
```

---

## Limitations

Current implementation limitations:

- **No key rotation** - Cannot re-encrypt with new key (planned for future)
- **No client-side encryption** - Only server-side supported (client-side planned)
- **Memory-based** - Entire file loaded for encryption (chunked planned)
- **Single key** - One master key for all files (per-user keys planned)

---

## Security Considerations

### Key Storage

- Never commit keys to git
- Use environment variables or secrets manager
- Store backup copy securely (password manager, HSM, etc.)

### Access Control

Encryption protects files at rest. Access control is separate:

- API keys control who can upload/download
- Encryption prevents access if disk is compromised
- Both work together for defense in depth

### Backup Encryption

Database backups contain file metadata (paths, sizes) but not file content. File backups should also be encrypted or stored securely.

---

## Next Steps

- [File Storage API](./files.md) - Upload and download files
- [Bulk Operations](./bulk-operations.md) - Batch file operations
- [Setup Guide](../setup.md) - Initial server setup
