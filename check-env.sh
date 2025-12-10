#!/bin/bash
# Pre-flight environment validation for Docker deployment
# Run this BEFORE docker-compose up to catch configuration issues early

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}Storm Cloud - Environment Check${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

ERRORS=0
WARNINGS=0

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${RED}✗ ERROR: .env file not found${NC}"
    echo "  Fix: cp .env.template .env"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓${NC} .env file exists"

# Source the .env file
set -a
source .env
set +a

# Check SECRET_KEY
if [ -z "$SECRET_KEY" ]; then
    echo -e "${RED}✗ ERROR: SECRET_KEY is not set${NC}"
    ERRORS=$((ERRORS + 1))
elif [ "$SECRET_KEY" = "your-secret-key-here-change-in-production" ]; then
    echo -e "${RED}✗ ERROR: SECRET_KEY is still the placeholder value${NC}"
    echo ""
    echo "  Generate a new one:"
    echo -e "  ${BLUE}python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'${NC}"
    echo ""
    echo "  Then update .env:"
    echo -e "  ${BLUE}SECRET_KEY=<paste-generated-key-here>${NC}"
    echo ""
    ERRORS=$((ERRORS + 1))
else
    echo -e "${GREEN}✓${NC} SECRET_KEY is set"
fi

# Check POSTGRES_PASSWORD
if [ -z "$POSTGRES_PASSWORD" ]; then
    echo -e "${RED}✗ ERROR: POSTGRES_PASSWORD is not set${NC}"
    ERRORS=$((ERRORS + 1))
elif [ "$POSTGRES_PASSWORD" = "change-this-secure-password" ]; then
    echo -e "${YELLOW}⚠ WARNING: POSTGRES_PASSWORD is still the default value${NC}"
    echo "  For production, use a strong unique password"
    echo ""
    WARNINGS=$((WARNINGS + 1))
else
    echo -e "${GREEN}✓${NC} POSTGRES_PASSWORD is set"
fi

# Check POSTGRES_HOST (should be 'db' for Docker)
if [ -n "$POSTGRES_HOST" ] && [ "$POSTGRES_HOST" != "db" ] && [ "$POSTGRES_HOST" != "localhost" ]; then
    echo -e "${YELLOW}⚠ WARNING: POSTGRES_HOST is set to '${POSTGRES_HOST}'${NC}"
    echo "  For Docker deployment, this should be 'db'"
    echo ""
    WARNINGS=$((WARNINGS + 1))
fi

# Summary
echo ""
echo -e "${BLUE}============================================${NC}"

if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}✗ Validation FAILED${NC}"
    echo -e "${RED}  Found ${ERRORS} error(s)${NC}"
    if [ $WARNINGS -gt 0 ]; then
        echo -e "${YELLOW}  Found ${WARNINGS} warning(s)${NC}"
    fi
    echo ""
    echo "Fix the errors above, then run:"
    echo -e "  ${BLUE}./check-env.sh${NC}      # Validate again"
    echo -e "  ${BLUE}docker-compose up -d${NC} # Start services"
    echo ""
    exit 1
else
    echo -e "${GREEN}✓ Validation PASSED${NC}"
    if [ $WARNINGS -gt 0 ]; then
        echo -e "${YELLOW}  Found ${WARNINGS} warning(s) (non-fatal)${NC}"
    fi
    echo ""
    echo "Ready to start! Run:"
    echo -e "  ${BLUE}docker-compose up -d${NC}"
    echo ""
fi
