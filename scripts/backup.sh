#!/bin/bash
set -e

# Auto-detect docker compose command
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    DOCKER_COMPOSE="docker compose"
fi

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration - auto-detect environment
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="stormcloud_backup_${TIMESTAMP}"

# Use environment variables if set, otherwise detect based on what exists
if [ -n "$BACKUPS_PATH" ]; then
    BACKUP_DIR="$BACKUPS_PATH"
elif [ -d "/var/stormcloud/backups" ]; then
    BACKUP_DIR="/var/stormcloud/backups"
else
    BACKUP_DIR="./backups"
fi

if [ -n "$UPLOADS_PATH" ]; then
    UPLOADS_DIR="$UPLOADS_PATH"
elif [ -d "/var/stormcloud/uploads" ]; then
    UPLOADS_DIR="/var/stormcloud/uploads"
else
    UPLOADS_DIR="./uploads"
fi

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}Storm Cloud Server - Backup${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "Backup destination: $BACKUP_DIR"
echo "Uploads source:     $UPLOADS_DIR"
echo ""

# Create backup directory
mkdir -p "$BACKUP_DIR"

echo -e "${GREEN}📦 Creating backup: ${BACKUP_NAME}${NC}"
echo ""

# Backup PostgreSQL database
echo -e "${YELLOW}1/2${NC} Backing up PostgreSQL database..."
$DOCKER_COMPOSE exec -T db pg_dump -U stormcloud stormcloud > "$BACKUP_DIR/${BACKUP_NAME}.sql"
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Database backup created: ${BACKUP_NAME}.sql"
else
    echo -e "${RED}✗${NC} Database backup failed!"
    exit 1
fi

# Backup uploads directory
echo -e "${YELLOW}2/2${NC} Backing up uploads directory..."
echo "    Source: $UPLOADS_DIR"
if [ -d "$UPLOADS_DIR" ]; then
    tar -czf "$BACKUP_DIR/${BACKUP_NAME}_uploads.tar.gz" -C "$(dirname "$UPLOADS_DIR")" "$(basename "$UPLOADS_DIR")"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} Uploads backup created: ${BACKUP_NAME}_uploads.tar.gz"
    else
        echo -e "${RED}✗${NC} Uploads backup failed!"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠${NC} No uploads directory found at $UPLOADS_DIR, skipping..."
fi

# Create backup manifest
cat > "$BACKUP_DIR/${BACKUP_NAME}_manifest.txt" <<EOF
Storm Cloud Server Backup
=========================
Date: $(date)
Timestamp: $TIMESTAMP

Paths Used:
- Backup directory: $BACKUP_DIR
- Uploads source: $UPLOADS_DIR

Files:
- ${BACKUP_NAME}.sql (PostgreSQL database dump)
- ${BACKUP_NAME}_uploads.tar.gz (Uploaded files)

Restore Instructions:
1. Stop the server: make down
2. Restore database:
   cat ${BACKUP_DIR}/${BACKUP_NAME}.sql | docker compose exec -T db psql -U stormcloud stormcloud
3. Restore uploads:
   tar -xzf ${BACKUP_DIR}/${BACKUP_NAME}_uploads.tar.gz -C $(dirname "$UPLOADS_DIR")
4. Start the server: make up
EOF

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}✓ Backup Complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "Backup location: ${BACKUP_DIR}/"
echo "Files created:"
echo "  - ${BACKUP_NAME}.sql"
echo "  - ${BACKUP_NAME}_uploads.tar.gz"
echo "  - ${BACKUP_NAME}_manifest.txt"
echo ""
echo "To restore this backup, run: ./scripts/restore.sh ${BACKUP_NAME}"
echo ""
