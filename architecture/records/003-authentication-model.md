# ADR 003: Authentication Model

**Status:** Accepted

## Context

Storm Cloud Server needs authentication for both CLI access and potential web dashboard access. The choice affects security, developer experience, and implementation complexity.

**Architectural Characteristics:**

- Security (protection against common attack vectors)
- Usability (developer experience for CLI and web)
- Maintainability (complexity of dual auth paths)
- Extensibility (adding OAuth2 or other providers later)

**Options Considered:**

1. **Session-based only** - Traditional Django sessions for all access
2. **Token-based only (JWT)** - Stateless tokens for all access
3. **API keys only** - Simple key-based authentication
4. **Hybrid** - Sessions for web, API keys for CLI/programmatic access

## Decision

Hybrid authentication (Option 4)

**Justification:**

1. CLI requires stateless auth - can't maintain session cookies easily
2. API keys are simpler than JWT refresh token flows for CLI use case
3. Web dashboard (proprietary layer) benefits from session security and CSRF protection
4. API keys are easy to generate, revoke, and scope
5. Can add OAuth2 later for third-party integrations without changing core auth

## Consequences

**Positive:**

- Right authentication method for each context
- API keys are simple to implement in CLI (single header)
- Sessions handle web security concerns automatically
- Keys can be scoped (read-only, full access, etc.) in future iterations

**Negative:**

- Two authentication paths to implement and maintain
- Must clearly document which endpoints accept which auth methods
- API key storage in CLI needs secure handling

**Accepted Trade-offs:**

- Implementation complexity of dual auth for better UX in each context
- CLI users must manage API key securely (their responsibility)

## Governance

**Fitness Functions:**

- All API endpoints must explicitly declare accepted auth methods in decorator/middleware
- API keys must be hashed before storage (never plaintext in database)
- Session endpoints must have CSRF protection enabled
- Authentication module cannot import from feature apps (auth is core infrastructure)
- Test coverage for both auth paths on all protected endpoints

**Manual Reviews:**

- New authentication method additions require security review
- Changes to API key scoping/permissions require architecture review
- Any endpoint auth method changes require PR justification