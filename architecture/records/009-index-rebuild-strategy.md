# ADR 009: Index Rebuild Strategy

**Status:** Accepted

## Context

Storm Cloud Server follows ADR 000's "Filesystem Wins" policy: the database is a rebuildable index, and the filesystem is the source of truth. This creates two critical requirements:

1. **Reconciliation** - Database must stay synchronized with filesystem reality
2. **Recovery** - Must handle index corruption, migration errors, or filesystem changes

**Architectural Characteristics:**

- Reliability (database accuracy matches filesystem reality)
- Recoverability (rebuild index from filesystem at any time)
- Auditability (detect and report discrepancies)
- Safety (prevent accidental data loss during cleanup)

**Options Considered:**

1. **Manual SQL queries** - Ad-hoc database fixes when desync detected
2. **Migration-only sync** - Fix discrepancies during Django migrations
3. **Background cron job** - Periodic reconciliation independent of user actions
4. **On-demand rebuild** - Management command + API endpoint when needed
5. **Hybrid approach** - On-demand + automated audit on startup

## Decision

Hybrid approach (Option 5) using Django 6.0 Tasks Framework:

**Pattern: Multi-Mode Index Reconciliation**

```
Filesystem (Source of Truth)
  ↓
IndexSyncService (core/services/index_sync.py)
  ├─ Mode: audit   → Report discrepancies only
  ├─ Mode: sync    → Add missing DB records
  ├─ Mode: clean   → Delete orphaned DB records (requires --force)
  └─ Mode: full    → Sync + clean (requires --force)
  ↓
Django Task (storage/tasks.py)
  ↓
Multiple Interfaces:
  ├─ Management Command (python manage.py rebuild_index)
  ├─ API Endpoint (POST /api/v1/index/rebuild/)
  ├─ Helper Script (./scripts/rebuild-index.sh)
  └─ Automated Audit (runs on container startup)
```

**Justification:**

1. **Django 6.0 Tasks** provides idempotent, serializable operations
2. **Service layer** (`IndexSyncService`) isolates business logic from Django
3. **Multiple modes** allow safe exploration (audit) before modification (sync/clean)
4. **Force flags** prevent accidental deletion of database records
5. **Automated audit** catches issues early without blocking startup
6. **CLI + API + Script** supports dev, ops, and programmatic workflows

## Implementation

### Service Layer

`core/services/index_sync.py`:
```python
class IndexSyncService:
    def __init__(self, storage_backend=None, user_id=None):
        # User filtering optional
        
    def sync(self, mode='audit', dry_run=False, force=False) -> IndexSyncStats:
        # audit: Report only
        # sync: Add missing DB records, update stale metadata
        # clean: Delete orphaned DB records (requires force=True)
        # full: sync + clean (requires force=True)
```

### Django Task

`storage/tasks.py`:
```python
@task()
def rebuild_storage_index(mode='audit', user_id=None, dry_run=False, force=False):
    service = IndexSyncService(user_id=user_id)
    stats = service.sync(mode=mode, dry_run=dry_run, force=force)
    return asdict(stats)  # JSON-serializable
```

### Management Command

```bash
python manage.py rebuild_index --mode audit
python manage.py rebuild_index --mode sync --dry-run
python manage.py rebuild_index --mode clean --force
python manage.py rebuild_index --mode full --force --user-id 123
```

### API Endpoint (Admin Only - P0-1 Security Fix)

**NOTE:** This endpoint requires admin privileges as of P0-1 security fix. For non-admin users, use the management command instead.

```bash
POST /api/v1/index/rebuild/
Authorization: Bearer <admin_api_key>

{
  "mode": "sync",
  "user_id": 123,  # optional
  "dry_run": false,
  "force": false
}

Response:
{
  "task_id": "abc123",
  "status": "SUCCESSFUL",
  "result": {
    "users_scanned": 1,
    "files_on_disk": 10,
    "files_in_db": 8,
    "missing_in_db": 2,
    "orphaned_in_db": 0,
    "records_created": 2,
    "records_deleted": 0,
    "records_skipped": 0,
    "errors": []
  }
}
```

### Automated Startup Audit

`entrypoint.sh` (Step 6/7):
```bash
echo "🔍 Auditing database index..."
python manage.py rebuild_index --mode audit || echo "⚠️  Index audit found discrepancies"
```

Non-blocking - container starts even if audit finds issues.

## Consequences

**Positive:**

- Database can be rebuilt from filesystem at any time (ADR 000 enforcement)
- Multiple safe modes prevent accidental data loss
- Automated audit catches desync early
- Metadata updates (file size, content_type) handled automatically
- ShareLink CASCADE protection prevents breaking foreign key relationships
- Idempotent operations (safe to run multiple times)
- Supports both system-wide and per-user reconciliation

**Negative:**

- Additional code complexity (service layer + task + command + API)
- `clean` and `full` modes require explicit `--force` flag (safety vs convenience)
- Filesystem scanning can be slow for large user bases
- Test infrastructure requires filesystem setup/teardown

**Accepted Trade-offs:**

- Safety over convenience (`--force` required for destructive operations)
- Eventual consistency (audit runs on startup but doesn't block)
- Synchronous execution (ImmediateBackend) over background processing (simplicity for MVP)

## Governance

**Fitness Functions:**

- Index rebuild must be idempotent (running twice produces same result)
- Database records with active ShareLinks must never be deleted (CASCADE protection)
- `clean` and `full` modes must require `force=True` to execute
- Filesystem wins: if file exists on disk but not in DB, DB must be updated (not file deleted)
- Metadata updates must check both size and content_type (stale detection)
- API endpoint must return task_id and serializable results
- Management command must succeed even if zero changes needed
- Startup audit must not block container launch

**Manual Reviews:**

- Changes to reconciliation logic require test coverage review
- New modes require architecture review
- CASCADE protection changes require data loss risk assessment

## Related Decisions

- ADR 000: Risk Matrix - Mitigates "Index desync" risk
- ADR 001: Service Granularity - Service layer stays within monolith
- ADR 002: Storage Backend Strategy - Works with abstract storage interface
- ADR 004: API Versioning - Endpoint under `/api/v1/`
- ADR 005: CLI-First Development - Management command designed for CLI workflow

## References

- Django 6.0 Tasks Documentation: https://docs.djangoproject.com/en/stable/topics/tasks/
- Implementation: `core/services/index_sync.py`, `storage/tasks.py`
- Tests: `core/tests/test_index_sync.py` (24 tests), `storage/tests/test_tasks.py` (15 tests)
- Management Command: `storage/management/commands/rebuild_index.py`
- API Endpoint: `storage/api.py:820-914`
- Helper Script: `scripts/rebuild-index.sh`
