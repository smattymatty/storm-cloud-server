# Storm Cloud Server - Task Completion Checklist

When completing a task (feature, bug fix, refactoring, etc.), follow this checklist to ensure quality and consistency.

## 1. Code Quality

### Type Hints
- [ ] All new functions have type annotations
- [ ] Return types are specified
- [ ] No use of `Any` unless absolutely necessary
- [ ] Run `mypy .` to verify type checking passes

### Code Style
- [ ] Follow existing patterns in the codebase
- [ ] Use flat API responses (CLI-friendly)
- [ ] Keep code simple and readable
- [ ] Add docstrings for complex functions/classes
- [ ] Remove any debug print statements or commented-out code

### Security
- [ ] User-provided paths validated with `normalize_path()` and `validate_filename()`
- [ ] Appropriate permission classes on new API endpoints
- [ ] Rate limiting applied to new endpoints
- [ ] No sensitive data in logs or error messages
- [ ] SQL injection prevention (use ORM, avoid raw queries)

## 2. Testing

### Test Coverage
- [ ] Write tests for new functionality
- [ ] Update existing tests if behavior changed
- [ ] Run full test suite: `python manage.py test`
- [ ] All tests pass
- [ ] Coverage remains high: `coverage run --source='.' manage.py test && coverage report`

### Test Quality
- [ ] Use factories for test data (avoid hardcoded values)
- [ ] Test happy path and error cases
- [ ] Test edge cases (empty strings, null values, boundary conditions)
- [ ] Test authentication/authorization rules
- [ ] Test rate limiting if applicable

## 3. Database

### Migrations
- [ ] Create migrations if models changed: `python manage.py makemigrations`
- [ ] Review migration file for correctness
- [ ] Run migrations: `python manage.py migrate`
- [ ] Test migration rollback if applicable
- [ ] No hardcoded IDs or user data in migrations

### Data Integrity
- [ ] Foreign keys have appropriate `on_delete` behavior
- [ ] Indexes added for frequently queried fields
- [ ] No N+1 query issues (use `select_related` / `prefetch_related`)

## 4. API Design

### Endpoints
- [ ] Follow REST conventions (GET/POST/PUT/PATCH/DELETE)
- [ ] Use appropriate HTTP status codes
- [ ] Consistent URL structure under `/api/v1/`
- [ ] Clear, descriptive endpoint names

### Request/Response
- [ ] Request validation via serializers
- [ ] Flat response structure (CLI-friendly)
- [ ] Meaningful error messages
- [ ] Pagination for list endpoints
- [ ] Field names follow snake_case convention

### Documentation
- [ ] OpenAPI schema generated correctly
- [ ] Test endpoints in Swagger UI: `/api/schema/swagger-ui/`
- [ ] Add examples for complex endpoints
- [ ] Update README.md API table if new endpoints added

## 5. Architecture

### Design Adherence
- [ ] Follows modular monolith pattern (no cross-app imports except via public interfaces)
- [ ] Respects app boundaries
- [ ] Uses storage backend abstraction (not direct filesystem access)
- [ ] Filesystem wins - database is rebuildable index

### File Organization
- [ ] New code in appropriate app
- [ ] Shared utilities in `core/utils.py` or `core/services/`
- [ ] No circular imports
- [ ] Follows project structure conventions

## 6. Performance

### Optimization
- [ ] No unnecessary database queries
- [ ] Large file operations handle streaming (not loading into memory)
- [ ] Appropriate caching if needed
- [ ] Rate limiting protects against abuse

### Index Rebuild Compatibility
- [ ] If file operations added, ensure they update database correctly
- [ ] Test with index rebuild: `python manage.py rebuild_index --mode audit`
- [ ] Filesystem operations logged or traceable

## 7. Environment & Configuration

### Settings
- [ ] New settings added to `.env.template`
- [ ] Default values provided
- [ ] Documentation added for new environment variables
- [ ] Settings validated in `_core/settings/base.py`

### Backwards Compatibility
- [ ] Breaking changes documented
- [ ] Migration path provided for existing deployments
- [ ] No hardcoded values that should be configurable

## 8. Documentation

### Code Documentation
- [ ] Complex logic has explanatory comments
- [ ] Architecture decisions reference ADRs
- [ ] Public functions/classes have docstrings

### User Documentation
- [ ] Update README.md if user-facing features changed
- [ ] Update CLAUDE.md if architecture patterns changed
- [ ] Add examples for new CLI commands (design target)
- [ ] Update API endpoint table in README.md

### Developer Documentation
- [ ] Update ADRs if architecture decisions made
- [ ] Document new environment variables
- [ ] Add memory/context files if needed

## 9. Integration

### Dependencies
- [ ] No new dependencies without justification
- [ ] New dependencies added to `requirements.txt`
- [ ] Dependencies pinned to major version (e.g., `>=3.16.0,<4.0`)

### Related Systems
- [ ] GoToSocial integration tested if share link features changed
- [ ] Storage quota checks if file operations added
- [ ] Email verification works if authentication changed

## 10. Final Checks

### System Checks
- [ ] `python manage.py check` passes
- [ ] `python manage.py check --deploy` passes (production settings)
- [ ] No new warnings in console output

### Manual Testing
- [ ] Test feature manually in Swagger UI or with curl
- [ ] Test with valid and invalid inputs
- [ ] Test authentication/authorization
- [ ] Test error handling

### Clean Up
- [ ] Remove temporary files, debug code, print statements
- [ ] No `import pdb` or breakpoints left in code
- [ ] No TODO comments without GitHub issues
- [ ] Commit messages are clear and descriptive

---

## Quick Pre-Commit Commands

```bash
# Activate virtual environment
source venv/bin/activate

# Run tests
python manage.py test

# Type checking
mypy .

# Django checks
python manage.py check

# Index rebuild audit (if file operations changed)
python manage.py rebuild_index --mode audit -v 2
```

## Post-Task Deployment

If deployed to production:
- [ ] Test on staging environment first
- [ ] Run migrations on production: `make deploy-app`
- [ ] Monitor logs for errors after deployment
- [ ] Verify backup exists before destructive operations
- [ ] Update GoToSocial integration if share link features changed