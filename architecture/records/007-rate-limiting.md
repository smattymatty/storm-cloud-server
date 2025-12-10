# ADR 007: Rate Limiting Strategy

**Status:** Accepted

## Context

Storm Cloud Server needs rate limiting to prevent abuse on the hosted instance and protect resource-intensive endpoints.

**Architectural Characteristics:**

- Security (brute force protection)
- Availability (prevent resource exhaustion)
- Simplicity (minimal new dependencies)

**Options Considered:**

1. **DRF Throttling** - Built into Django REST Framework
2. **django-ratelimit** - Decorator-based, flexible
3. **Nginx-level** - Rate limit at reverse proxy
4. **Redis + custom** - Roll our own with token bucket

## Decision

DRF Throttling (Option 1) for application-level limits, Nginx for connection-level limits in production.

**Justification:**

1. DRF throttling already in the stack—zero new dependencies
2. Per-user and per-endpoint granularity
3. Works with cache backend (memory for dev, Redis for prod)
4. Nginx handles connection floods before they hit Django

## Consequences

**Positive:**

- No new dependencies
- Configurable per-endpoint
- Cache backend swappable

**Negative:**

- Memory backend doesn't share state across workers
- Must add Redis for production horizontal scaling

**Accepted Trade-offs:**

- Memory cache sufficient for single-instance MVP
- Redis becomes requirement when scaling horizontally

## Implementation

**Default Rates:**

| Scope | Rate | Endpoints |
|-------|------|-----------|
| `login` | 5/min | /auth/login/ |
| `auth` | 10/hour | /auth/tokens/, /auth/register/ |
| `uploads` | 100/hour | /files/*/upload/ |
| `downloads` | 500/hour | /files/*/download/ |
| `default` | 1000/hour | Everything else |

**Settings:**
```python
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'login': '5/min',
        'auth': '10/hour',
        'uploads': '100/hour',
        'downloads': '500/hour',
        'user': '1000/hour',
    }
}
```

## Governance

**Fitness Functions:**

- Rate limit headers present in responses (X-RateLimit-*)
- 429 responses include Retry-After header
- Auth endpoints must use stricter throttle class

**Manual Reviews:**

- Rate limit changes require load testing validation