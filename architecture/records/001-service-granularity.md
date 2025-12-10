# ADR 001: Service Granularity

**Status:** Accepted

## Context

Storm Cloud Server needs a deployment architecture. The choice affects development velocity, operational complexity, and future scalability.

**Architectural Characteristics:**

- Deployability (single target vs multiple services)
- Maintainability (clear boundaries between modules)
- Scalability (independent scaling capability)
- Simplicity (operational overhead for small team)

**Options Considered:**

1. **Monolith** - Single Django project, all functionality in one deployable
2. **Modular Monolith** - Single Django project, strict app boundaries, extractable later
3. **Microservices** - Separate services for storage, auth, CMS from the start

## Decision

Modular Monolith (Option 2)

**Justification:**

1. Small team cannot absorb microservices operational overhead
2. Django apps provide natural module boundaries without deployment complexity
3. Mercury can test internal API boundaries as if they were service boundaries
4. Shared database simplifies transactionality for file + CMS operations
5. Can extract to separate services later if scaling demands require it

## Consequences

**Positive:**

- Single deployment target simplifies DevOps
- Shared database means ACID transactions across modules
- Faster iteration during early development
- Lower infrastructure costs

**Negative:**

- Must maintain strict discipline on app boundaries
- Risk of coupling creep if boundaries aren't enforced
- Cannot scale modules independently

**Accepted Trade-offs:**

- Trading operational simplicity now for potential extraction work later
- Betting that independent scaling won't be needed in the first year

## Governance

**Fitness Functions:**

- No direct model imports across app boundaries (only through `services.py`)
- No cross-app foreign keys without documented exception
- Import graph analysis to detect circular dependencies
- Each app must expose functionality only through defined service interfaces

**Manual Reviews:**

- New app creation requires architecture review
- Any cross-app database relationship requires justification in PR