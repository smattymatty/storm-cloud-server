# ADR 004: API Versioning Strategy

**Status:** Accepted

## Context

Storm Cloud Server exposes an API consumed by the CLI and potentially third-party clients. The versioning strategy affects backward compatibility, client upgrade paths, and maintenance burden.

**Architectural Characteristics:**

- Evolvability (ability to change API without breaking clients)
- Usability (clear contracts for CLI and third-party developers)
- Maintainability (burden of supporting multiple versions)
- Observability (debugging and logging clarity)

**Options Considered:**

1. **URL path versioning** - `/api/v1/files/`, `/api/v2/files/`
2. **Header versioning** - `Accept: application/vnd.stormcloud.v1+json`
3. **Query parameter versioning** - `/api/files/?version=1`
4. **No versioning** - Single API, breaking changes require all clients to update

## Decision

URL path versioning (Option 1)

**Justification:**

1. Explicit and visible - version is obvious in logs, documentation, CLI code
2. Easy to implement in Django URL routing
3. CLI can hardcode version path, simple to update on major releases
4. Can run multiple versions simultaneously during migration periods
5. Industry standard for public APIs (GitHub, Stripe, etc.)

## Consequences

**Positive:**

- Clear contract between CLI version and API version
- Can deprecate old versions with clear timelines
- Easy to test - hit different URL paths
- No magic headers or query params to debug

**Negative:**

- URL duplication across versions if not structured carefully
- Must maintain old versions during deprecation windows
- Breaking changes require new version (can't sneak them in)

**Accepted Trade-offs:**

- Overhead of version maintenance for stability guarantees to CLI users
- Version proliferation risk if not disciplined about what constitutes breaking change

## Governance

**Fitness Functions:**

- All API endpoints must be under versioned URL namespace (`/api/v{n}/`)
- No breaking changes to existing version without new version number
- Deprecated versions must return `Deprecation` header with sunset date
- API response schemas must be validated against versioned OpenAPI specs
- CLI tests must run against declared compatible API version

**Manual Reviews:**

- New API version creation requires architecture review
- Breaking change definition disputes escalate to architecture review
- Version deprecation timeline requires documented migration path for clients