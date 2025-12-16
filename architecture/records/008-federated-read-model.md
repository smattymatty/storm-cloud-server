# ADR 008: Federated Read Model via ActivityPub

**Status:** Accepted

## Context

Organizations need transparent, auditable communication about operations. Traditional approaches (email lists, RSS, status pages, Twitter) are either centralized, gatekept, dying, or platform-dependent.

The Fediverse (ActivityPub) provides decentralized, sovereign, federated infrastructure that reaches existing social networks without requiring users to create new accounts.

**Architectural Characteristics:**

- Transparency (public audit trail of operations)
- Sovereignty (own infrastructure, not platform-dependent)
- Decentralization (no single point of failure)
- Reach (federate to existing Mastodon/Fediverse networks)

**Options Considered:**

1. **Webhooks** - Requires recipient infrastructure, not federated
2. **RSS feeds** - One-way, dying technology, requires aggregators
3. **Email lists** - Centralized, gatekept, spam-prone
4. **Twitter/X API** - Platform-dependent, algorithmic, not sovereign
5. **ActivityPub (Fediverse)** - Federated, open protocol, sovereign infrastructure

## Decision

Post significant system events to GoToSocial (ActivityPub), treating the Fediverse timeline as a **federated read model** for organizational activity.

**Pattern: Federated Read Model**

```
Write Model (ShareLink.create)
  → Signal Handler (post_save, non-blocking)
    → GoToSocial API (HTTP POST)
      → Fediverse Timeline (federated read model)
        → Followers (any ActivityPub server)
```

**Justification:**

1. Organizations (co-ops, open source, collectives) need transparent operations
2. Fediverse provides reach without centralized platforms
3. Users consume via existing Mastodon accounts (no new accounts needed)
4. Posts are durable, linkable, searchable (better than ephemeral feeds)
5. Generalizes to other event types (releases, docs, moderation logs)

**Implementation: Share Link Auto-Posting**

When share link created → Post to timeline:
```
🔗 New file shared: report.pdf
📦 2.3 MB • ⏰ Expires in 7 days
→ https://cloud.example.com/s/abc123
```

When share link revoked/expired → Delete post from timeline (configurable)

## Consequences

**Positive:**

- Public audit trail of file sharing operations
- Organizations own communication infrastructure
- Reaches users on existing Fediverse accounts
- Posts are permanent, linkable, searchable
- Foundation for future governance features (proposals, voting)

**Negative:**

- Posts are public by design (privacy trade-off for transparency)
- Requires GoToSocial/Mastodon server running
- Federated posts cannot be fully deleted (ActivityPub limitation)
- Must respect rate limits to avoid spam classification

**Accepted Trade-offs:**

- Eventual consistency - posts may lag behind events
- Dependency on external service - graceful degradation if unavailable
- Spam risk - high-frequency events need aggregation

## Governance

**Fitness Functions:**

- Share link creation must succeed even if social posting fails (core operation non-blocking)
- Failed social posts must add warning to API response (user visibility)
- Social posting must not add >50ms to request latency (async signal handler)
- Expired share links with social posts must be cleaned up within 24 hours (cron job)
- All social posts must include link back to source system (traceability)

**Manual Reviews:**

- New event types for social posting require architecture review
- Changes to post format require user impact assessment
- Rate limit changes require spam impact analysis

## Implementation Notes

**Signal-Based Architecture:**

```python
@receiver(post_save, sender=ShareLink)
def post_share_link_to_social(sender, instance, created, **kwargs):
    if not created or not settings.GOTOSOCIAL_AUTO_POST_ENABLED:
        return
    
    try:
        client = GoToSocialClient.from_settings()
        response = client.post_status(format_share_link_post(instance))
        instance.posted_to_social = True
        instance.social_post_id = response["id"]
        instance.save()
    except Exception as e:
        logger.error(f"Social post failed: {e}")
        add_social_warning("SOCIAL_POST_FAILED", "...")
        # Share link still created - graceful degradation
```

**Graceful Degradation:**

API response when GoToSocial unavailable:
```json
{
  "id": "abc123",
  "posted_to_social": false,
  "warnings": [{"code": "SOCIAL_POST_FAILED", "message": "..."}]
}
```

**Configuration:**

```bash
GOTOSOCIAL_AUTO_POST_ENABLED=true       # Feature flag
GOTOSOCIAL_DOMAIN=social.example.com    # Fediverse server
GOTOSOCIAL_TOKEN=xxx                     # API token
GOTOSOCIAL_DELETE_ON_REVOKE=true        # Auto-cleanup
```

**Generalization:**

This pattern applies to any event worth broadcasting:
- Software releases → Version announcements
- Dataset updates → Data availability notices
- Documentation changes → Change logs
- Moderation actions → Transparency logs
- Community events → Event announcements

## Related Decisions

- ADR 001: Service Granularity (signals stay within monolith)
- ADR 003: Authentication Model (API key pattern reused for GoToSocial token)
- ADR 005: CLI-First Development (CLI can display social post status)

## References

- ActivityPub W3C Spec: https://www.w3.org/TR/activitypub/
- GoToSocial: https://docs.gotosocial.org/
- Implementation: `social/` app, `storage/migrations/0005_add_social_posting_fields.py`
- Documentation: `docs_content/social/gotosocial.md`
