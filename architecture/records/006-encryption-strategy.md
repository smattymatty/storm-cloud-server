# ADR 006: Encryption Strategy

**Status:** Accepted

## Context

Storm Cloud Server stores user files. Encryption at rest protects data confidentiality. The strategy affects security posture, implementation complexity, and future monetization options.

**Architectural Characteristics:**

- Security (data protection at rest)
- Simplicity (implementation and operational complexity)
- Evolvability (path to client-side encryption)
- Usability (transparent to users vs key management burden)

**Options Considered:**

1. **No encryption** - Rely on filesystem/cloud provider permissions only
2. **Server-side encryption (server holds keys)** - Transparent encryption, server manages keys
3. **Client-side encryption (user holds keys)** - CLI encrypts before upload, server never sees plaintext
4. **Phased approach** - Server-side now, client-side optional later

## Decision

Phased approach (Option 4) — server-side encryption as default, with architecture that supports future client-side encryption.

**Justification:**

1. Server-side encryption is sufficient for self-hosted deployments where operator is the user
2. Backblaze B2 provides server-side encryption at storage layer (SSE-B2)
3. Local storage backend can use filesystem encryption or application-layer encryption
4. Client-side encryption is a monetization differentiator for hosted instance ("zero-knowledge storage")
5. Delaying client-side avoids complexity before product-market fit is proven
6. Metadata schema must include encryption method field from day one to avoid migration pain

**Future Client-Side Design Constraints:**

- File metadata must store: `encryption_method` (none/server/client), `key_id` (nullable), `encrypted_filename` (nullable)
- API responses must not assume server can read file contents
- CLI must be designed to handle local encryption/decryption path

## Consequences

**Positive:**

- Simple implementation for v1
- Self-hosters get encryption without complexity
- Clear upgrade path to premium "zero-knowledge" tier
- Metadata schema is future-proof

**Negative:**

- Hosted instance users must trust operator until client-side ships
- Server-side encryption doesn't protect against operator or legal compulsion
- Must resist temptation to build features that require server-side file access

**Accepted Trade-offs:**

- Shipping faster with weaker security model, with explicit plan to strengthen
- Features requiring server-side processing (search, thumbnails) may need rework or exclusion for client-encrypted files

## Governance

**Fitness Functions:**

- All stored files must have `encryption_method` set in metadata
- No direct file content access outside of storage abstraction layer
- File processing code must check encryption method and fail gracefully for client-encrypted files
- Test suite must include encrypted file roundtrip verification

**Manual Reviews:**

- Any feature requiring server-side file content access requires architecture review
- Client-side encryption implementation requires security review before release
- Key management strategy requires dedicated ADR before implementation