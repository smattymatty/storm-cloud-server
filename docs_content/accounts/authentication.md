---
title: Authentication Guide
published: 2025-12-12
modified: 2025-12-12
tags:
  - api
  - authentication
  - accounts
  - security
---

Complete guide to authentication in Storm Cloud Server. Learn how to register, login, manage API keys, and secure your account.

---

## Authentication Methods

Storm Cloud supports **two authentication methods**:

1. **API Keys** (Recommended) - For CLI tools and programmatic access
2. **Session Cookies** - For web browser access and Swagger UI

**Note:** JWT token authentication is planned but not yet implemented.

---

## Quick Start

### 1. Register an Account

```bash
curl -X POST http://localhost:8000/api/v1/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "email": "alice@example.com",
    "password": "SecurePass123!"
  }'
```

**Response:**
```json
{
  "id": 2,
  "username": "alice",
  "email": "alice@example.com",
  "is_verified": false,
  "message": "Registration successful. Please check your email to verify your account."
}
```

### 2. Verify Your Email

Check your email for the verification link, then:

```bash
curl -X POST http://localhost:8000/api/v1/auth/verify-email/ \
  -H "Content-Type: application/json" \
  -d '{"token": "VERIFICATION_TOKEN_FROM_EMAIL"}'
```

### 3. Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -c cookies.txt \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "password": "SecurePass123!"
  }'
```

### 4. Create an API Key

```bash
curl -X POST http://localhost:8000/api/v1/auth/tokens/ \
  -b cookies.txt \
  -H "Content-Type: application/json" \
  -d '{"name": "My CLI Key"}'
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "My CLI Key",
  "key": "abc123xyz456def789ghi012jkl345mno678pqr901stu234vwx567yza890bcd123",
  "created_at": "2025-12-12T10:00:00Z",
  "last_used_at": null
}
```

**⚠️ IMPORTANT:** Save the `key` value immediately! It's only shown once and cannot be retrieved later.

---

## API Key Authentication (Recommended)

API keys are the **primary authentication method** for Storm Cloud. Use them for:
- CLI tools
- Scripts and automation
- Mobile apps
- Third-party integrations

### Creating API Keys

#### Method 1: Via API (Recommended)

```bash
# Login first to get a session
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -c cookies.txt \
  -H "Content-Type: application/json" \
  -d '{"username": "youruser", "password": "yourpass"}'

# Create API key
curl -X POST http://localhost:8000/api/v1/auth/tokens/ \
  -b cookies.txt \
  -H "Content-Type: application/json" \
  -d '{"name": "CLI Access"}'
```

#### Method 2: Via Makefile (Easiest)

```bash
make api_key
# Enter your username when prompted
```

#### Method 3: Via Django Shell

```bash
make shell  # Select [1] Web server

# In Python shell:
from accounts.models import User, APIKey
user = User.objects.get(username='youruser')
key = APIKey.objects.create(user=user, name='CLI Key')
print(f"Your API key: {key.key}")
```

#### Method 4: Via Django Admin

1. Login at `http://localhost:8000/admin/`
2. Navigate to **Accounts → API Keys**
3. Click **Add API Key**
4. Select user and name the key
5. Save and copy the generated key

### Using API Keys

Include the API key in the `Authorization` header with the `Bearer` scheme:

```bash
curl http://localhost:8000/api/v1/dirs/ \
  -H "Authorization: Bearer YOUR_API_KEY_HERE"
```

**Python Example:**
```python
import requests

headers = {"Authorization": f"Bearer {api_key}"}
response = requests.get(
    "http://localhost:8000/api/v1/dirs/",
    headers=headers
)
print(response.json())
```

**JavaScript Example:**
```javascript
fetch("http://localhost:8000/api/v1/dirs/", {
  headers: {
    "Authorization": `Bearer ${apiKey}`
  }
})
.then(res => res.json())
.then(data => console.log(data));
```

### Managing API Keys

**List All Your Keys:**

```bash
curl http://localhost:8000/api/v1/auth/tokens/ \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**Response:**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "CLI Key",
    "prefix": "abc123",
    "created_at": "2025-12-12T10:00:00Z",
    "last_used_at": "2025-12-12T15:30:00Z"
  },
  {
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "name": "Mobile App",
    "prefix": "xyz789",
    "created_at": "2025-12-11T09:00:00Z",
    "last_used_at": null
  }
]
```

**Revoke a Key:**

```bash
curl -X POST http://localhost:8000/api/v1/auth/tokens/{KEY_ID}/revoke/ \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**Response:**
```json
{
  "message": "API key revoked successfully"
}
```

### API Key Security

- **Hashing:** Keys are hashed with SHA-256 in the database
- **One-time display:** Only shown once during creation
- **Cannot retrieve:** Must create new key if lost
- **Automatic revocation:** Invalidated when user account is deleted
- **Last used tracking:** Monitor key activity

**Best Practices:**
- ✅ Store keys in environment variables
- ✅ Use separate keys for different applications
- ✅ Rotate keys every 90 days
- ✅ Revoke compromised keys immediately
- ✅ Use meaningful names ("Production Server", "Dev Laptop")
- ❌ Never commit keys to git
- ❌ Never share keys via email/chat
- ❌ Never hardcode in source code

---

## Session Authentication (Web Browser)

Session authentication uses Django's built-in session framework. Use this for:
- Web dashboards
- Swagger UI (`/api/docs/`)
- Browser-based access

### Login

**Endpoint:** `POST /api/v1/auth/login/`

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -c cookies.txt \
  -H "Content-Type: application/json" \
  -d '{
    "username": "youruser",
    "password": "yourpassword"
  }'
```

**Response:**
```json
{
  "message": "Login successful",
  "user": {
    "id": 1,
    "username": "youruser",
    "email": "you@example.com",
    "is_verified": true
  }
}
```

The session cookie is automatically set and stored in `cookies.txt`.

### Using Session Cookies

Include the cookie in subsequent requests:

```bash
curl http://localhost:8000/api/v1/dirs/ \
  -b cookies.txt
```

### Logout

**Endpoint:** `POST /api/v1/auth/logout/`

```bash
curl -X POST http://localhost:8000/api/v1/auth/logout/ \
  -b cookies.txt
```

**Response:**
```json
{
  "message": "Logout successful"
}
```

---

## Account Registration

### Create Account

**Endpoint:** `POST /api/v1/auth/register/`

**Request:**
```json
{
  "username": "newuser",
  "email": "newuser@example.com",
  "password": "SecurePass123!"
}
```

**Password Requirements:**
- Minimum 8 characters
- Cannot be too common (e.g., "password123")
- Cannot be entirely numeric
- Cannot be too similar to username

**Response (Success):**
```json
{
  "id": 2,
  "username": "newuser",
  "email": "newuser@example.com",
  "is_verified": false,
  "created_at": "2025-12-12T10:00:00Z",
  "message": "Registration successful. Please check your email to verify your account."
}
```

**Response (Error):**
```json
{
  "error": "username",
  "detail": "A user with that username already exists."
}
```

### Email Verification

After registration, a verification email is sent (if email backend is configured).

**Verify Email:**

**Endpoint:** `POST /api/v1/auth/verify-email/`

**Request:**
```json
{
  "token": "verification-token-from-email"
}
```

**Response:**
```json
{
  "message": "Email verified successfully. You can now log in."
}
```

**Resend Verification Email:**

**Endpoint:** `POST /api/v1/auth/resend-verification/`

**Request:**
```json
{
  "email": "your@example.com"
}
```

**Response:**
```json
{
  "message": "Verification email sent if account exists and is unverified."
}
```

---

## Account Management

### Get Current User Info

**Endpoint:** `GET /api/v1/auth/me/`

**Request:**
```bash
curl http://localhost:8000/api/v1/auth/me/ \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**Response:**
```json
{
  "id": 1,
  "username": "youruser",
  "email": "you@example.com",
  "is_verified": true,
  "is_active": true,
  "is_staff": false,
  "date_joined": "2025-12-01T10:00:00Z",
  "storage_quota_bytes": 1073741824,
  "storage_used_bytes": 52428800
}
```

### Deactivate Account

**Endpoint:** `POST /api/v1/auth/deactivate/`

Deactivates your account. You can be reactivated by an admin.

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/deactivate/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"confirm": true}'
```

**Response:**
```json
{
  "message": "Account deactivated successfully"
}
```

### Delete Account Permanently

**Endpoint:** `DELETE /api/v1/auth/delete/`

**⚠️ WARNING:** This permanently deletes your account and all files. Cannot be undone!

**Request:**
```bash
curl -X DELETE http://localhost:8000/api/v1/auth/delete/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"confirm": "DELETE"}'
```

**Response:**
```json
{
  "message": "Account and all associated data deleted successfully"
}
```

---

## Rate Limiting

Storm Cloud implements rate limiting to prevent abuse:

| Endpoint | Authenticated | Anonymous (IP-based) |
|----------|---------------|----------------------|
| `/auth/login/` | 5 req/min | 10 req/hour |
| `/auth/register/` | 10 req/hour | 5 req/hour |
| `/auth/tokens/` (POST) | 10 req/hour | N/A |
| `/auth/verify-email/` | N/A | 10 req/hour |

**Rate Limit Headers:**
```http
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 8
X-RateLimit-Reset: 1702328400
```

**Rate Limit Exceeded Response:**
```json
{
  "error": "Request was throttled",
  "detail": "Request was throttled. Expected available in 45 seconds."
}
```

---

## Error Responses

All authentication errors follow this format:

```json
{
  "error": "error_type",
  "detail": "Human-readable error message"
}
```

### Common Error Codes

| HTTP Status | Error | Description |
|-------------|-------|-------------|
| 400 | `invalid_input` | Missing or invalid fields |
| 401 | `invalid_credentials` | Wrong username/password |
| 401 | `invalid_token` | Malformed or expired API key |
| 403 | `email_not_verified` | Email verification required |
| 403 | `account_inactive` | Account deactivated |
| 409 | `username_exists` | Username already taken |
| 409 | `email_exists` | Email already registered |
| 429 | `rate_limit_exceeded` | Too many requests |

---

## Security Features

### Password Security

- **Hashing:** Argon2 (Django default)
- **Validation:** Django's password validators
- **Requirements:** 8+ chars, not too common, not entirely numeric

### Account Security

- **Email verification:** Optional (configured via settings)
- **Rate limiting:** All endpoints protected
- **Session security:** HTTPS enforced in production, secure cookies
- **CSRF protection:** Enabled for session auth

### Planned Features

- Two-factor authentication (2FA)
- Failed login tracking
- Account lockout after repeated failures
- Password reset via email
- OAuth2 integration

---

## Configuration

Configure authentication in `.env`:

```env
# Registration Settings
ALLOW_REGISTRATION=true
REQUIRE_EMAIL_VERIFICATION=false

# Email Backend (for verification emails)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=noreply@yourdomain.com

# Session Settings
SESSION_COOKIE_AGE=1209600  # 2 weeks
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SECURE=True  # HTTPS only in production
```

---

## Code Examples

### Python SDK Pattern

```python
import requests
from typing import Optional

class StormCloudClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def _request(self, method: str, endpoint: str, **kwargs):
        url = f"{self.base_url}/api/v1{endpoint}"
        response = requests.request(method, url, headers=self.headers, **kwargs)
        response.raise_for_status()
        return response.json()

    def get_user_info(self):
        return self._request("GET", "/auth/me/")

    def list_api_keys(self):
        return self._request("GET", "/auth/tokens/")

    def create_api_key(self, name: str):
        return self._request("POST", "/auth/tokens/", json={"name": name})

# Usage
client = StormCloudClient(
    base_url="http://localhost:8000",
    api_key="your-api-key-here"
)

user = client.get_user_info()
print(f"Logged in as: {user['username']}")
```

### Bash Script with API Key Storage

```bash
#!/bin/bash
# Save as: ~/.local/bin/stormcloud-auth

# Configuration
STORMCLOUD_CONFIG_DIR="$HOME/.config/stormcloud"
STORMCLOUD_API_KEY_FILE="$STORMCLOUD_CONFIG_DIR/api_key"

# Ensure config directory exists
mkdir -p "$STORMCLOUD_CONFIG_DIR"
chmod 700 "$STORMCLOUD_CONFIG_DIR"

# Load API key
if [ -f "$STORMCLOUD_API_KEY_FILE" ]; then
    API_KEY=$(cat "$STORMCLOUD_API_KEY_FILE")
else
    echo "Error: API key not found. Run 'stormcloud-auth setup' first."
    exit 1
fi

# Make authenticated request
curl http://localhost:8000/api/v1/auth/me/ \
  -H "Authorization: Bearer $API_KEY"
```

---

## Related Documentation

- [API Quickstart](../api-quickstart.md) - Complete API reference
- [Setup Guide](../setup.md) - Get Storm Cloud running
- [File Storage API](../storage/files.md) - Upload and manage files
- [Security Policy](../../SECURITY.md) - Security best practices

---

## Getting Help

- **GitHub Issues:** [storm-cloud-server/issues](https://github.com/smattymatty/storm-cloud-server/issues)
- **Interactive Docs:** Visit `/api/docs/` on your running server
- **Source Code:** Check `accounts/api.py` for implementation details
