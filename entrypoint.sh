#!/bin/bash
set -e

echo "============================================"
echo "Storm Cloud Server - Container Starting"
echo "============================================"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================
# 1. VALIDATE ENVIRONMENT VARIABLES
# ============================================
echo ""
echo "Step 1/7: Validating environment variables..."

VALIDATION_FAILED=0

# Check SECRET_KEY
if [ -z "$SECRET_KEY" ]; then
    echo -e "${RED}ERROR: SECRET_KEY environment variable is not set${NC}"
    echo "Fix: Add SECRET_KEY to your .env file"
    echo "Generate one with: python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'"
    VALIDATION_FAILED=1
elif [ "$SECRET_KEY" = "your-secret-key-here-change-in-production" ]; then
    echo -e "${RED}ERROR: SECRET_KEY is still the placeholder value${NC}"
    echo "Fix: Change SECRET_KEY in your .env file to a unique random value"
    echo "Generate one with: python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'"
    VALIDATION_FAILED=1
else
    echo -e "${GREEN}✓${NC} SECRET_KEY is set"
fi

# Check PostgreSQL configuration
if [ -z "$POSTGRES_PASSWORD" ]; then
    echo -e "${RED}ERROR: POSTGRES_PASSWORD environment variable is not set${NC}"
    echo "Fix: Add POSTGRES_PASSWORD to your .env file"
    VALIDATION_FAILED=1
elif [ "$POSTGRES_PASSWORD" = "change-this-secure-password" ]; then
    echo -e "${YELLOW}WARNING: POSTGRES_PASSWORD is still the default value${NC}"
    echo "For production, change this to a strong unique password"
else
    echo -e "${GREEN}✓${NC} PostgreSQL configuration set"
fi

# Exit if validation failed
if [ $VALIDATION_FAILED -eq 1 ]; then
    echo ""
    echo -e "${RED}============================================${NC}"
    echo -e "${RED}Environment validation FAILED${NC}"
    echo -e "${RED}============================================${NC}"
    echo "Container will not start until these issues are fixed."
    echo "Edit your .env file and restart: docker compose up -d"
    exit 1
fi

echo -e "${GREEN}Environment validation passed${NC}"

# ============================================
# 2. VALIDATE DATA DIRECTORY MOUNTS
# ============================================
echo ""
echo "Step 2/8: Validating data directory mounts..."

# Check uploads directory exists
if [ ! -d "/app/uploads" ]; then
    echo -e "${RED}ERROR: /app/uploads directory does not exist!${NC}"
    echo "This indicates the uploads volume is not mounted correctly."
    echo "Fix: Check docker-compose.yml volume configuration"
    exit 1
fi

# Check uploads directory is writable
if ! touch /app/uploads/.mount_test 2>/dev/null; then
    echo -e "${RED}ERROR: /app/uploads is not writable!${NC}"
    echo "Fix: Check volume permissions and ownership"
    exit 1
fi
rm -f /app/uploads/.mount_test

# Create mount marker if it doesn't exist (helps detect ephemeral mounts)
if [ ! -f "/app/uploads/.mounted" ]; then
    echo "Creating mount marker file..."
    touch /app/uploads/.mounted 2>/dev/null || true
fi

echo -e "${GREEN}✓${NC} Data directory mounts validated"

# ============================================
# 3. WAIT FOR DATABASE
# ============================================
echo ""
echo "Step 3/8: Waiting for database to be ready..."

# Use POSTGRES_* environment variables
DB_HOST="${POSTGRES_HOST}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_USER="${POSTGRES_USER:-stormcloud}"
DB_NAME="${POSTGRES_DB:-stormcloud}"

RETRY_COUNT=0
MAX_RETRIES=30

until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" > /dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo -e "${RED}ERROR: Database did not become ready after ${MAX_RETRIES} seconds${NC}"
        echo "Check database logs with: docker compose logs db"
        exit 1
    fi
    echo "Waiting for database... (${RETRY_COUNT}/${MAX_RETRIES})"
    sleep 1
done

echo -e "${GREEN}✓${NC} Database is ready"

# ============================================
# 4. RUN MIGRATIONS
# ============================================
echo ""
echo "Step 4/8: Running database migrations..."

python manage.py migrate --noinput

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Migrations completed successfully"
else
    echo -e "${RED}ERROR: Migrations failed${NC}"
    exit 1
fi

# ============================================
# 5. COLLECT STATIC FILES
# ============================================
echo ""
echo "Step 5/8: Collecting static files..."

python manage.py collectstatic --noinput --clear

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Static files collected"
else
    echo -e "${YELLOW}WARNING: Static file collection failed (non-fatal)${NC}"
fi

# ============================================
# 6. BUILD SPELLBOOK MARKDOWN
# ============================================
echo ""
echo "Step 6/8: Building Spellbook markdown files..."

python manage.py spellbook_md

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Spellbook markdown built"
else
    echo -e "${YELLOW}WARNING: Spellbook build failed (non-fatal)${NC}"
fi

# ============================================
# 7. REBUILD STORAGE INDEX
# ============================================
echo ""
echo "Step 7/8: Checking storage index..."

python manage.py rebuild_index --mode audit -v 0

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Storage index audit complete"
else
    echo -e "${YELLOW}WARNING: Storage index audit failed (non-fatal)${NC}"
fi

# ============================================
# 8. START APPLICATION
# ============================================
echo ""
echo "Step 8/8: Starting application server..."
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}Storm Cloud Server is starting...${NC}"
echo -e "${GREEN}============================================${NC}"
echo "Workers: 3"
echo "Port: 8000"
echo "Health check: http://localhost:8000/api/v1/health/"
echo ""

# Execute the CMD from Dockerfile
exec "$@"
