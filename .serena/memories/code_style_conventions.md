# Storm Cloud Server - Code Style & Conventions

## General Principles
- **Type hints everywhere** - All functions must have type annotations
- **Flat API responses** - CLI-friendly, avoid nested structures
- **Simple over clever** - Readable, maintainable code over complex abstractions
- **Follow existing patterns** - Consistency across the codebase

## Type Checking with MyPy

### Configuration Strategy
The project uses **gradual typing** with strict enforcement for critical modules.

#### General Settings (Relaxed by Default)
- `disallow_untyped_defs = false` - Allows functions without type hints (gradual adoption)
- `disallow_incomplete_defs = false` - Allows partial type hints
- `warn_return_any = false` - Allows Any returns
- `check_untyped_defs = true` - Still checks bodies of untyped functions
- `ignore_missing_imports = true` - Ignore missing type stubs for external libraries

#### Strict Mode for Critical Modules
The following modules require **full type hints** (security/business-critical):
- `storage.api` - File operations
- `accounts.authentication` - Auth security
- `accounts.api` - User management
- `social.client` - External HTTP calls
- `core.utils` - Shared utilities

Strict settings for these modules:
- `disallow_untyped_defs = true` - All functions must have type hints
- `disallow_incomplete_defs = true` - No partial type hints
- `warn_return_any = true` - Warn if function returns Any

#### Django Integration
- Uses `mypy_django_plugin` and `mypy_drf_plugin` for ORM support
- Django migrations excluded from type checking
- Django ORM false positives suppressed with `disable_error_code = ["attr-defined", "misc"]`

### Running Type Checks
```bash
mypy .
```

## Code Organization

### File Structure
Each Django app follows standard structure:
```
app_name/
├── migrations/       # Database migrations (auto-generated)
├── tests/           # Test files (test_*.py)
├── management/      # Custom management commands
│   └── commands/
├── __init__.py
├── admin.py         # Django admin configuration
├── api.py           # DRF API views
├── apps.py          # App configuration
├── models.py        # Database models
├── serializers.py   # DRF serializers
├── signals.py       # Django signals
└── utils.py         # Utility functions
```

### Naming Conventions
- **Classes**: PascalCase (`UserProfile`, `APIKey`)
- **Functions/Methods**: snake_case (`normalize_path`, `validate_filename`)
- **Constants**: UPPER_SNAKE_CASE (`MAX_UPLOAD_SIZE`, `DEFAULT_EXPIRY_DAYS`)
- **Private members**: Leading underscore (`_internal_helper`)
- **API views**: Descriptive suffix (`RegistrationView`, `FileUploadView`)

## Django REST Framework Patterns

### View Classes
Use DRF generic views and mixins:
- `APIView` for custom logic
- `CreateAPIView`, `ListAPIView`, etc. for standard CRUD
- Explicit permission classes for each view
- Explicit authentication classes if different from defaults

### Serializers
- Keep serializers close to models they represent
- Use explicit field declarations (avoid `fields = '__all__'`)
- Add validation methods for complex rules
- Use `SerializerMethodField` for computed fields

### Response Format
Keep responses flat and CLI-friendly:
```python
# Good (flat)
{"file_path": "doc.txt", "size_bytes": 1024, "created": "2024-01-01"}

# Avoid (nested)
{"file": {"metadata": {"path": "doc.txt", "size": 1024}, "dates": {"created": "2024-01-01"}}}
```

## Testing

### Test Organization
- One test file per module: `test_<module_name>.py`
- Use `factory-boy` for test data generation
- Keep factories in `tests/factories.py`

### Test Structure
```python
from django.test import TestCase
from .factories import UserFactory

class MyFeatureTestCase(TestCase):
    def setUp(self):
        self.user = UserFactory()
    
    def test_specific_behavior(self):
        # Arrange
        # Act
        # Assert
        pass
```

## Documentation

### Docstrings
- Use for complex functions and classes
- Keep simple for self-explanatory code
- Focus on "why" not "what"

### Comments
- Explain non-obvious decisions
- Reference ADRs for architecture choices
- Keep comments updated when code changes

## Security Patterns

### Path Validation
Always use `core.utils.normalize_path()` and `core.utils.validate_filename()` for user-provided paths:
```python
from core.utils import normalize_path, PathValidationError

try:
    safe_path = normalize_path(user_path)
except PathValidationError:
    # Handle invalid path
```

### Authentication
- Use `@permission_classes([IsAuthenticated])` for protected endpoints
- Use `@permission_classes([IsAdminUser])` for admin endpoints
- Use `@permission_classes([AllowAny])` explicitly for public endpoints

### Rate Limiting
Apply appropriate throttle classes to views:
- `LoginThrottle` - Login attempts
- `AuthThrottle` - Registration, API key creation
- `UploadThrottle` - File uploads
- `DownloadThrottle` - File downloads
- See `core/throttling.py` for available throttles

## Error Handling

### Exceptions
- Use DRF exceptions: `ValidationError`, `PermissionDenied`, `NotFound`
- Create custom exceptions in `core/exceptions.py` for domain-specific errors
- Always provide meaningful error messages

### Response Codes
- 200 OK - Successful retrieval
- 201 Created - Resource created
- 204 No Content - Successful deletion
- 400 Bad Request - Validation error
- 401 Unauthorized - Authentication required
- 403 Forbidden - Permission denied
- 404 Not Found - Resource doesn't exist
- 429 Too Many Requests - Rate limit exceeded
- 500 Internal Server Error - Server error (avoid exposing details)