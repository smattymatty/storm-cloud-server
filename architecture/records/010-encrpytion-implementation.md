# ADR 010: Encryption Implementation

**Status:** Accepted

**Supersedes:** Builds on ADR 006 (Encryption Strategy)

## Context

ADR 006 established the phased encryption strategy: server-side encryption first, client-side later. This ADR specifies the implementation details for Phase 1 (server-side encryption).

**Requirements:**

1. Protect data at rest against disk theft, backup leaks, hosting provider access
2. Support both single-server-key and per-user-key modes
3. Transparent to end users (no key management burden)
4. Migration path for existing unencrypted files
5. Extensible architecture for future client-side encryption

**Architectural Characteristics:**

- Security (strong encryption, secure key handling)
- Simplicity (configuration via .env, transparent operation)
- Evolvability (clean path to client-side and other modes)
- Performance (minimal overhead for encrypt/decrypt operations)

## Decision

### Algorithm

**AES-256-GCM** (Galois/Counter Mode)

**Justification:**

1. Authenticated encryption — integrity and confidentiality in one operation
2. Industry standard, NIST approved
3. Hardware acceleration on modern CPUs (AES-NI)
4. Includes authentication tag — detects tampering
5. Python `cryptography` library provides robust implementation

### Key Architecture

**Two server-side modes:**

| Mode | Key Source | Use Case |
|------|------------|----------|
| `server` | Single master key from .env | Simple self-hosted deployments |
| `server-user` | Per-user key derived from master key + user_id | Multi-tenant, user isolation |

**Key Derivation (server-user mode):**

```python
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

def derive_user_key(master_key: bytes, user_id: int) -> bytes:
    """Derive a unique 256-bit key for each user."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"stormcloud-user-key-v1",  # Static salt, versioned
        info=f"user-{user_id}".encode(),
    )
    return hkdf.derive(master_key)
```

**Justification for per-user keys:**

1. User A's key compromise doesn't expose User B's files
2. User deletion can conceptually "destroy" their key (files become unrecoverable)
3. Future: per-user key rotation without re-encrypting all files
4. Managed hosting clients get meaningful isolation

### Configuration

**.env variables:**

```bash
# Encryption method: none, server, server-user, client (future)
STORAGE_ENCRYPTION_METHOD=server

# Master encryption key (required if method != none)
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
STORAGE_ENCRYPTION_KEY=<base64-encoded-32-byte-key>

# Optional: Key ID for rotation tracking
STORAGE_ENCRYPTION_KEY_ID=1
```

**Validation on startup:**

```python
# settings.py or app ready()
if STORAGE_ENCRYPTION_METHOD != 'none':
    if not STORAGE_ENCRYPTION_KEY:
        raise ImproperlyConfigured(
            "STORAGE_ENCRYPTION_KEY required when encryption is enabled"
        )
    # Validate key length (32 bytes for AES-256)
    key_bytes = base64.urlsafe_b64decode(STORAGE_ENCRYPTION_KEY)
    if len(key_bytes) != 32:
        raise ImproperlyConfigured(
            "STORAGE_ENCRYPTION_KEY must be 32 bytes (256 bits)"
        )
```

### File Format

**Encrypted file structure:**

```
+----------------+------------------+------------+------------------+
| Version (1B)   | Nonce (12B)      | Tag (16B)  | Ciphertext (var) |
+----------------+------------------+------------+------------------+
```

- **Version byte:** `0x01` for AES-256-GCM (allows future algorithm changes)
- **Nonce:** 12 bytes, randomly generated per file (GCM standard)
- **Tag:** 16 bytes, authentication tag from GCM
- **Ciphertext:** Encrypted file contents

**Why include version byte:**

Future-proofing. If we add ChaCha20-Poly1305 or client-side encryption, the version byte tells us how to decrypt without checking metadata first.

### Database Schema

**StoredFile model updates:**

```python
class EncryptionMethod(models.TextChoices):
    NONE = 'none', 'No encryption'
    SERVER = 'server', 'Server-side (master key)'
    SERVER_USER = 'server-user', 'Server-side (per-user key)'
    CLIENT = 'client', 'Client-side (user holds key)'  # Future

class StoredFile(models.Model):
    # ... existing fields ...
    
    # Encryption metadata
    encryption_method = models.CharField(
        max_length=20,
        choices=EncryptionMethod.choices,
        default=EncryptionMethod.NONE,
    )
    encryption_key_id = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Key identifier for rotation tracking"
    )
    encrypted_size = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Size of encrypted file (includes overhead)"
    )
    # Original size stored in existing 'size' field
```

### Service Layer

**New service: `core/services/encryption.py`**

```python
class EncryptionService:
    """Handles all encryption/decryption operations."""
    
    def __init__(self, method: str = None):
        self.method = method or settings.STORAGE_ENCRYPTION_METHOD
        self.master_key = self._load_master_key()
    
    def encrypt_file(self, plaintext: bytes, user_id: int = None) -> bytes:
        """Encrypt file contents. Returns encrypted blob with header."""
        if self.method == 'none':
            return plaintext
        
        key = self._get_key(user_id)
        nonce = os.urandom(12)
        
        cipher = AESGCM(key)
        ciphertext = cipher.encrypt(nonce, plaintext, None)
        
        # ciphertext includes tag (last 16 bytes)
        return b'\x01' + nonce + ciphertext
    
    def decrypt_file(self, encrypted: bytes, user_id: int = None) -> bytes:
        """Decrypt file contents. Handles version detection."""
        if self.method == 'none':
            return encrypted
        
        version = encrypted[0]
        if version != 0x01:
            raise ValueError(f"Unknown encryption version: {version}")
        
        nonce = encrypted[1:13]
        ciphertext_with_tag = encrypted[13:]
        
        key = self._get_key(user_id)
        cipher = AESGCM(key)
        
        return cipher.decrypt(nonce, ciphertext_with_tag, None)
    
    def _get_key(self, user_id: int = None) -> bytes:
        """Get appropriate key based on method and user."""
        if self.method == 'server':
            return self.master_key
        elif self.method == 'server-user':
            if user_id is None:
                raise ValueError("user_id required for server-user encryption")
            return self._derive_user_key(user_id)
        else:
            raise ValueError(f"Encryption method {self.method} not implemented")
    
    def _derive_user_key(self, user_id: int) -> bytes:
        """Derive per-user key from master key."""
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"stormcloud-user-key-v1",
            info=f"user-{user_id}".encode(),
        )
        return hkdf.derive(self.master_key)
```

### Storage Backend Integration

**Modify storage backends to use EncryptionService:**

```python
# storage/backends/base.py
class BaseStorageBackend:
    def __init__(self):
        self.encryption = EncryptionService()
    
    def save(self, path: str, content: bytes, user_id: int = None) -> dict:
        """Save file with encryption if enabled."""
        encrypted = self.encryption.encrypt_file(content, user_id)
        # ... write encrypted to backend ...
        return {
            'encryption_method': self.encryption.method,
            'encryption_key_id': settings.STORAGE_ENCRYPTION_KEY_ID,
            'encrypted_size': len(encrypted),
            'original_size': len(content),
        }
    
    def load(self, path: str, user_id: int = None) -> bytes:
        """Load and decrypt file."""
        encrypted = self._read_from_backend(path)
        return self.encryption.decrypt_file(encrypted, user_id)
```

### Migration Command

**Management command: `encrypt_existing_files`**

```bash
# Audit only - show what would be encrypted
python manage.py encrypt_existing_files --mode audit

# Encrypt with dry-run
python manage.py encrypt_existing_files --mode encrypt --dry-run

# Actually encrypt (requires --force)
python manage.py encrypt_existing_files --mode encrypt --force

# Single user only
python manage.py encrypt_existing_files --mode encrypt --force --user-id 123
```

**Behavior:**

1. Scan all StoredFile records where `encryption_method='none'`
2. For each file:
   - Read plaintext from storage
   - Encrypt using configured method
   - Write encrypted file (new path or overwrite based on backend)
   - Update StoredFile metadata
   - Verify decryption roundtrip
3. Report statistics

**Safety:**

- `--force` required for actual encryption
- Verify roundtrip before marking complete
- Batch processing with progress output
- Resumable (skips already-encrypted files)

### Extensibility for Client-Side

**Future client-side flow (not implemented now):**

```
CLI encrypts locally
  ↓
Uploads ciphertext + encrypted_filename
  ↓
Server stores without ability to decrypt
  ↓
Download returns ciphertext
  ↓
CLI decrypts locally
```

**Architecture prepared for this:**

1. `encryption_method='client'` already in choices
2. `EncryptionService.encrypt_file()` can return plaintext passthrough for client mode
3. API responses already include encryption_method in metadata
4. StoredFile.encrypted_filename field ready for filename privacy

**What client-side will need (future ADR):**

- CLI-side encryption implementation
- Key derivation from user passphrase
- Secure key storage on client
- Web UI WebCrypto integration
- Key recovery/escrow options

## Consequences

**Positive:**

- Files encrypted at rest with modern authenticated encryption
- Per-user key isolation for multi-tenant deployments
- Migration path for existing files
- Clean extensibility for client-side later
- Transparent to users (no key management)
- Version byte allows algorithm evolution

**Negative:**

- Encryption overhead (~29 bytes per file + compute)
- Master key in .env requires secure deployment practices
- Key loss = data loss (no recovery without key)
- Server-side doesn't protect against full server compromise

**Accepted Trade-offs:**

- Server holds keys (acceptable for Phase 1, client-side addresses later)
- Single master key per deployment (per-user derivation provides isolatWhy client-side encryption is hard:

    Key management (user loses key = data gone forever, no recovery)
    Server can't search, index, or preview encrypted content
    Sharing files between users becomes a cryptographic puzzle
    Web UI needs browser-based crypto (WebCrypto API)
    CLI needs encryption/decryption logic

Why it's your moat:

Nobody in the "self-hosted cloud storage" space does this well. Nextcloud's E2E encryption is notoriously janky. Most solutions punt on it entirely.

If you nail this, "Canadian data sovereignty with zero-knowledge encryption" is a real differentiator, not marketing fluff.ion)
- Migration is manual command (not automatic, gives operator control)

## Security Considerations

**Key Management:**

- Master key should be generated with cryptographically secure RNG
- Store .env securely (not in git, proper file permissions)
- Consider secrets management (Vault, AWS Secrets Manager) for production
- Document key backup procedures

**Threat Model (Server-Side):**

| Threat | Protected? |
|--------|------------|
| Disk theft | ✅ Yes |
| Backup leaks | ✅ Yes |Why client-side encryption is hard:

    Key management (user loses key = data gone forever, no recovery)
    Server can't search, index, or preview encrypted content
    Sharing files between users becomes a cryptographic puzzle
    Web UI needs browser-based crypto (WebCrypto API)
    CLI needs encryption/decryption logic

Why it's your moat:

Nobody in the "self-hosted cloud storage" space does this well. Nextcloud's E2E encryption is notoriously janky. Most solutions punt on it entirely.

If you nail this, "Canadian data sovereignty with zero-knowledge encryption" is a real differentiator, not marketing fluff.
| Hosting provider snooping | ✅ Yes |
| Database breach (metadata only) | ✅ Yes (files still encrypted) |
| Full server compromise | ❌ No (attacker gets key) |
| Legal compulsion | ❌ No (operator can decrypt) |

Last two threats require client-side encryption (Phase 2).

## Governance

**Fitness Functions:**

- All new file uploads must set `encryption_method` in metadata
- Encrypted files must roundtrip correctly (decrypt(encrypt(x)) == x)
- Key derivation must be deterministic (same user_id → same key)
- Version byte must be checked before decryption
- Storage backends must not access file contents without going through EncryptionService
Why client-side encryption is hard:

    Key management (user loses key = data gone forever, no recovery)
    Server can't search, index, or preview encrypted content
    Sharing files between users becomes a cryptographic puzzle
    Web UI needs browser-based crypto (WebCrypto API)
    CLI needs encryption/decryption logic

Why it's your moat:

Nobody in the "self-hosted cloud storage" space does this well. Nextcloud's E2E encryption is notoriously janky. Most solutions punt on it entirely.

If you nail this, "Canadian data sovereignty with zero-knowledge encryption" is a real differentiator, not marketing fluff.
**Manual Reviews:**

- Changes to encryption algorithm require security review
- Key derivation changes require cryptography review
- Migration command changes require data safety review

## Implementation Checklist

- [ ] Add `cryptography` to requirements.txt
- [ ] Create `core/services/encryption.py`
- [ ] Update StoredFile model with encryption fields
- [ ] Create migration for new fields
- [ ] Integrate EncryptionService with storage backends
- [ ] Create `encrypt_existing_files` management command
- [ ] Add .env.example with encryption configuration
- [ ] Update deployment docs
- [ ] Add tests for encryption roundtrip
- [ ] Add tests for per-user key derivation
- [ ] Add tests for migration command

## Related Decisions

- ADR 002: Storage Backend Strategy — Encryption integrates at backend level
- ADR 006: Encryption Strategy — This implements Phase 1
- ADR 009: Index Rebuild — May need awareness of encryption state
- Future ADR: Key Rotation Strategy
- Future ADR: Client-Side Encryption Implementation

## References

- NIST SP 800-38D: Recommendation for GCM Mode
- Python cryptography library: https://cryptography.io/
- HKDF RFC 5869: https://tools.ietf.org/html/rfc5869