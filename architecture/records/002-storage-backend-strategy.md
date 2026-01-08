# ADR 002: Storage Backend Strategy

**Status:** Accepted

**Extended by:** ADR 006 (Encryption Strategy), ADR 010 (Encryption Implementation)

## Context

Storm Cloud needs to store user files somewhere. The choice affects self-hosting viability, production scalability, and vendor lock-in.

**Architectural Characteristics:**

- Deployability (self-hosted vs cloud deployments)
- Extensibility (adding new storage backends)
- Testability (fast local testing without network dependencies)
- Vendor independence (avoiding cloud lock-in)

**Options Considered:**

1. **Local filesystem only** - Files stored on server disk
2. **Backblaze B2 only** - Cloud object storage, S3-compatible API
3. **Pluggable backend** - Abstract interface with multiple implementations
4. **Local with B2 sync** - Hybrid approach

## Decision

Pluggable backend (Option 3) with local filesystem as default, Backblaze B2 as first cloud adapter.

**Justification:**

1. Self-hosters want local storage with no external dependencies
2. Production deployments need scalable object storage
3. Django's storage backend pattern already supports this abstraction
4. Backblaze B2 is cost-effective and S3-compatible without AWS lock-in
5. Can add other backends later without changing core code

## Consequences

**Positive:**

- Maximum deployment flexibility
- Development and testing use local storage (fast, no network)
- Production uses B2 (scalable, durable, cheap)
- No vendor lock-in to AWS ecosystem
- Encryption integrates at backend level - transparent to all callers (ADR 010)

**Negative:**

- Must maintain storage interface abstraction
- Testing matrix includes multiple backends
- Backend-specific edge cases may surface over time

**Accepted Trade-offs:**

- Additional abstraction layer for broader applicability
- Backblaze B2 as primary cloud target may limit users who want AWS-native

## Governance

**Fitness Functions:**

- All file operations must go through abstract storage interface (no direct filesystem calls outside storage module)
- Test suite runs against both local and B2 backends in CI
- Storage interface methods must have consistent return types across all backends
- No backend-specific code outside of backend implementation files
- All backends must use `EncryptionService` for encrypt/decrypt operations (ADR 010)
- Backend `save()` must return encryption metadata (method, key_id, encrypted_size)

**Manual Reviews:**

- New storage backend implementations require architecture review
- Any changes to storage interface contract require review of all existing backends
- Encryption integration changes require security review

## Related Decisions

- ADR 006: Encryption Strategy - Encryption happens at backend level, transparent to callers
- ADR 009: Index Rebuild Strategy - Works with abstract storage interface
- ADR 010: Encryption Implementation - Defines `EncryptionService` integration in backends