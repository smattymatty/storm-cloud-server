# ADR 005: CLI-First Development Strategy

**Status:** Accepted

## Context

Storm Cloud Server requires a client interface. The relationship between server API design and client needs must be established before implementation begins.

**Architectural Characteristics:**

- Usability (CLI ergonomics for primary user workflow)
- Evolvability (API design that serves future clients)
- Testability (tight feedback loop between consumer and producer)
- Simplicity (clean mapping between commands and endpoints)

**Options Considered:**

1. **Server-first** - Design API based on internal data models, build CLI to consume it
2. **CLI-first** - Design CLI commands based on user workflows, shape API to serve them
3. **Parallel** - Design both simultaneously, reconcile differences as they emerge
4. **Spec-first** - Write OpenAPI spec, generate both server and client stubs

## Decision

CLI-first development (Option 2)

**Justification:**

1. The CLI is the primary interface for v1 - no web dashboard ships initially
2. CLI commands represent actual user workflows, not abstract CRUD operations
3. Designing CLI first surfaces real UX requirements before API solidifies
4. Prevents server-side abstractions that make sense internally but are awkward to consume
5. API endpoints should map cleanly to CLI commands - if a command feels clunky, the API is wrong
6. Self-dogfooding: building the CLI immediately exposes API pain points

**Design Principle:**

If a CLI command requires multiple API calls, awkward data transformation, or feels unnatural to type, that's a signal to revisit the API design - not to add complexity to the CLI.

## Consequences

**Positive:**

- API is shaped by real usage patterns
- CLI ergonomics are prioritized from the start
- Tight feedback loop between consumer needs and producer design
- Future clients (web dashboard, mobile) inherit a consumption-friendly API

**Negative:**

- May require API refactoring as CLI evolves
- Server implementation waits on CLI design decisions
- Risk of over-fitting API to CLI-specific patterns

**Accepted Trade-offs:**

- Slower initial velocity for better long-term API design
- CLI-specific conveniences may need abstraction when other clients arrive

## Governance

**Fitness Functions:**

- No CLI command should require more than one API call for its primary operation
- API response payloads must contain all data needed for CLI display (no N+1 fetches)
- CLI command execution time budget: single API call must complete in < 500ms for standard operations
- Mercury performance tests run against CLI-equivalent API call patterns

**Manual Reviews:**

- New CLI commands require corresponding API design review before implementation
- API changes that break clean CLI mapping require justification
- Any multi-call CLI workflow requires documented exception rationale

## Implementation Notes

Development sequence:

1. Sketch CLI command and expected output
2. Define API endpoint(s) needed to support it
3. Implement server endpoint
4. Implement CLI command
5. Refine both based on actual usage

Example - `stormcloud files ls`:
```
CLI design:
  $ stormcloud files ls /photos
  vacation-2024/
  profile.jpg
  notes.md

API requirement:
  GET /api/v1/files/photos/
  Response: list of entries with type, name, size, modified date
  Must return enough data for CLI to format output.
  Must not require additional calls to distinguish files from directories.
```

If the API forces the CLI to make N+1 requests or parse awkward response structures, fix the API.