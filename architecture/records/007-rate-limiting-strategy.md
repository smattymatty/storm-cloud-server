# ADR 007: Rate Limiting Strategy

**Status:** Accepted
**Date:** 2024-12-10
**Deciders:** Architecture Team

## Context

Storm Cloud Server needs rate limiting to prevent abuse on the hosted instance and protect resource-intensive endpoints. As a self-hostable cloud storage platform with API key authentication, we need to protect against:

- Brute force login attacks
- API key farming/abuse
- Spam user registration
- Resource exhaustion from file uploads/downloads
- General DoS attacks

**Architectural Characteristics:**

- **Security**: Prevent brute force and credential stuffing attacks
- **Availability**: Protect against resource exhaustion and DoS
- **Simplicity**: Minimal new dependencies, straightforward configuration
- **Flexibility**: Different limits for different endpoint types

**Options Considered:**

1. **DRF Throttling** - Built into Django REST Framework
   - ✅ Zero new dependencies (already using DRF)
   - ✅ Per-user and per-endpoint granularity
   - ✅ Automatic 429 responses with Retry-After headers
   - ❌ Memory backend doesn't share state across workers

2. **django-ratelimit** - Decorator-based rate limiting
   - ✅ Very flexible, decorator-based
   - ✅ Works with cache backends
   - ❌ Additional dependency
   - ❌ Less integrated with DRF

3. **Nginx-level Rate Limiting** - Reverse proxy limits
   - ✅ Handles connection floods before hitting Django
   - ✅ Very performant
   - ❌ Less granular (no per-user limits)
   - ❌ Deployment-specific

4. **Redis + Custom Implementation** - Roll our own with token bucket
   - ✅ Complete control
   - ❌ Significant development overhead
   - ❌ Reinventing the wheel

## Decision

**Use DRF Throttling (Option 1) for application-level limits**, with Nginx rate limiting as optional additional protection in production deployments.

**Justification:**

1. DRF throttling is already in our stack—zero new dependencies
2. Provides the granularity we need (per-user, per-endpoint)
3. Works with Django's cache backend (memory for dev, Redis for prod)
4. Automatic integration with DRF error handling
5. Environment-configurable rates align with our 12-factor approach
6. Nginx can be added later for connection-level protection without code changes

## Implementation Details

### Rate Limit Tiers

| Throttle Class | Rate | Applied To | Rationale |
|----------------|------|------------|-----------|
| `LoginRateThrottle` | 5/min | `/auth/login/` | Prevent brute force password attacks |
| `AuthRateThrottle` | 10/hour | `/auth/register/`, `/auth/tokens/` | Prevent spam registration and API key farming |
| `UploadRateThrottle` | 100/hour | `/files/*/upload/` | Manage bandwidth and storage resources |
| `DownloadRateThrottle` | 500/hour | `/files/*/download/` | Higher than upload but still bounded |
| `UserRateThrottle` | 1000/hour | All authenticated endpoints (default) | Generous limit for normal CLI usage |

### Configuration

**Settings.py:**
```python
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'login': config('THROTTLE_LOGIN_RATE', default='5/min'),
        'auth': config('THROTTLE_AUTH_RATE', default='10/hour'),
        'uploads': config('THROTTLE_UPLOAD_RATE', default='100/hour'),
        'downloads': config('THROTTLE_DOWNLOAD_RATE', default='500/hour'),
        'user': config('THROTTLE_USER_RATE', default='1000/hour'),
    }
}
```

**Custom Throttle Classes:**
```python
# core/throttling.py
class LoginRateThrottle(UserRateThrottle):
    scope = 'login'

class AuthRateThrottle(UserRateThrottle):
    scope = 'auth'
```

**View Application:**
```python
class LoginView(StormCloudBaseAPIView):
    throttle_classes = [LoginRateThrottle]
```

### Cache Backend

- **Development**: Django memory cache (sufficient for single worker)
- **Production**: Redis cache (required for multi-worker deployments)

## Consequences

### Positive

- ✅ Immediate protection against brute force and abuse
- ✅ Zero new dependencies
- ✅ Environment-configurable rates for different deployments
- ✅ Per-endpoint granularity protects resource-intensive operations
- ✅ Automatic 429 responses include Retry-After headers
- ✅ Works with both API key and session authentication
- ✅ No changes needed to existing views (default throttle applies)

### Negative

- ❌ Memory cache backend doesn't share state across workers (dev limitation)
- ❌ Requires Redis for production horizontal scaling
- ❌ Rate limits are approximate under high concurrency
- ❌ No built-in dashboard for monitoring throttle statistics

### Accepted Trade-offs

- **Memory cache for dev** is acceptable since we run single worker locally
- **Redis requirement for production** aligns with caching strategy anyway
- **Approximate limits** are acceptable for abuse prevention (don't need perfect accuracy)
- **No monitoring dashboard** can be added later with custom tooling

## Governance

### Fitness Functions

The following automated checks ensure rate limiting works correctly:

1. **Rate limit headers present**: All responses must include `X-RateLimit-Limit` and `X-RateLimit-Remaining`
2. **429 responses valid**: Throttled requests return 429 with `Retry-After` header
3. **Stricter limits on auth**: Login/register must use stricter throttle classes

### Manual Review Checklist

When changing rate limits:

- [ ] Load test validates new rates don't cause false positives
- [ ] Consider CLI user workflows (batch operations)
- [ ] Document rate limit changes in changelog
- [ ] Update .env.template and README

### Monitoring

Production deployments should monitor:

- Rate of 429 responses per endpoint
- Cache hit rate for throttle keys
- Average requests per user per hour

## Future Considerations

1. **Dynamic rate limits**: Consider per-user tier limits (free/paid)
2. **IP-based throttling**: Add for unauthenticated endpoints
3. **Burst limits**: Separate minute/hour limits for better UX
4. **Admin override**: Allow admins to temporarily increase limits
5. **Nginx layer**: Add connection-level limits in production reverse proxy

## References

- [DRF Throttling Documentation](https://www.django-rest-framework.org/api-guide/throttling/)
- [OWASP Rate Limiting Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html)
- Project requirement: CLI-first design (generous default limits)
- Project requirement: Self-hostable (environment-configurable)
