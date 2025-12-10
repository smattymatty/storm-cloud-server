#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "============================================"
echo "Storm Cloud Server - First-Time Setup"
echo "============================================"
echo ""

# Check if .env already exists
if [ -f .env ]; then
    echo -e "${YELLOW}⚠ WARNING: .env file already exists!${NC}"
    read -p "Overwrite it? [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Setup cancelled."
        exit 0
    fi
fi

# Copy template
echo -e "${GREEN}📄 Creating .env file from template...${NC}"
cp .env.template .env

# Generate SECRET_KEY
echo -e "${GREEN}🔑 Generating SECRET_KEY...${NC}"
if command -v python3 &> /dev/null; then
    SECRET_KEY=$(python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
    sed -i "s/SECRET_KEY=.*/SECRET_KEY=\"$SECRET_KEY\"/" .env
    echo -e "${GREEN}✓${NC} SECRET_KEY generated"
else
    echo -e "${YELLOW}⚠ WARNING: python3 not found. Please set SECRET_KEY manually in .env${NC}"
fi

# Prompt for PostgreSQL password
echo ""
echo -e "${GREEN}🐘 PostgreSQL Configuration${NC}"
echo "Enter a strong password for PostgreSQL:"
read -s POSTGRES_PASSWORD
echo ""
echo "Confirm password:"
read -s POSTGRES_PASSWORD_CONFIRM
echo ""

if [ "$POSTGRES_PASSWORD" != "$POSTGRES_PASSWORD_CONFIRM" ]; then
    echo -e "${RED}✗ ERROR: Passwords don't match!${NC}"
    exit 1
fi

if [ -z "$POSTGRES_PASSWORD" ]; then
    echo -e "${RED}✗ ERROR: Password cannot be empty!${NC}"
    exit 1
fi

sed -i "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$POSTGRES_PASSWORD/" .env
echo -e "${GREEN}✓${NC} PostgreSQL password set"

# Optional: Configure port
echo ""
read -p "Use default port 8000? [Y/n] " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Nn]$ ]]; then
    read -p "Enter port number: " WEB_PORT
    echo "WEB_PORT=$WEB_PORT" >> .env
    echo -e "${GREEN}✓${NC} Port set to $WEB_PORT"
else
    echo "WEB_PORT=8000" >> .env
    echo -e "${GREEN}✓${NC} Using default port 8000"
fi

# Add COMPOSE_PROJECT_NAME
echo "COMPOSE_PROJECT_NAME=stormcloud" >> .env

# Validate configuration
echo ""
echo -e "${GREEN}🔍 Validating configuration...${NC}"
if [ -f check-env.sh ]; then
    chmod +x check-env.sh
    if ./check-env.sh; then
        echo -e "${GREEN}✓${NC} Configuration valid"
    else
        echo -e "${RED}✗ Configuration validation failed${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠ WARNING: check-env.sh not found, skipping validation${NC}"
fi

# Final summary
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}✓ Setup Complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "Next steps:"
echo ""
echo "  1. Start the server (builds automatically):"
echo -e "     ${GREEN}make up${NC}"
echo ""
echo "  2. Create a superuser:"
echo -e "     ${GREEN}make superuser${NC}"
echo ""
echo "  3. Generate an API key:"
echo -e "     ${GREEN}make api_key${NC}"
echo ""
echo "  4. Access the API:"
echo "     http://localhost:${WEB_PORT:-8000}/api/v1/"
echo ""
echo -e "For more commands, run: ${GREEN}make help${NC}"
echo ""
