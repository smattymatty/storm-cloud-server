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
BLUE='\033[0;34m'
NC='\033[0m'

# Auto-detect environment paths
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
echo -e "${GREEN}Storm Cloud Server - Restore Backup${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "Backup source:      $BACKUP_DIR"
echo "Uploads destination: $UPLOADS_DIR"
echo ""

# List available backups
echo -e "${BLUE}Available backups:${NC}"
echo ""

BACKUPS=()
counter=1
while IFS= read -r manifest; do
    backup_name=$(basename "$manifest" | sed 's/_manifest.txt//')
    BACKUPS+=("$backup_name")

    # Show backup info
    if [ -f "$manifest" ]; then
        timestamp=$(echo "$backup_name" | grep -oP '\d{8}_\d{6}')
        date_part=${timestamp:0:8}
        time_part=${timestamp:9:6}
        formatted_date="${date_part:0:4}-${date_part:4:2}-${date_part:6:2}"
        formatted_time="${time_part:0:2}:${time_part:2:2}:${time_part:4:2}"

        echo -e "  ${GREEN}[$counter]${NC} $formatted_date at $formatted_time"
    fi
    ((counter++))
done < <(ls -t "$BACKUP_DIR"/*_manifest.txt 2>/dev/null)

if [ ${#BACKUPS[@]} -eq 0 ]; then
    echo -e "${RED}No backups found!${NC}"
    echo "Create a backup first with: make backup"
    exit 1
fi

echo ""

# Interactive selection
if [ -z "$1" ]; then
    read -p "Select backup number (1-${#BACKUPS[@]}) or 'q' to quit: " selection

    if [ "$selection" = "q" ] || [ "$selection" = "Q" ]; then
        echo "Cancelled."
        exit 0
    fi

    if ! [[ "$selection" =~ ^[0-9]+$ ]] || [ "$selection" -lt 1 ] || [ "$selection" -gt ${#BACKUPS[@]} ]; then
        echo -e "${RED}Invalid selection!${NC}"
        exit 1
    fi

    BACKUP_NAME="${BACKUPS[$((selection-1))]}"
else
    BACKUP_NAME="$1"
fi

# Check if backup exists
if [ ! -f "$BACKUP_DIR/${BACKUP_NAME}.sql" ]; then
    echo -e "${RED}✗ ERROR: Backup not found: ${BACKUP_NAME}${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}Selected backup: ${BACKUP_NAME}${NC}"

# Show backup manifest if available
if [ -f "$BACKUP_DIR/${BACKUP_NAME}_manifest.txt" ]; then
    echo ""
    echo -e "${BLUE}Backup Details:${NC}"
    cat "$BACKUP_DIR/${BACKUP_NAME}_manifest.txt" | grep -E "(Date:|Files:)" | sed 's/^/  /'
fi

# Confirm restore with typed confirmation
echo ""
echo -e "${RED}⚠️  WARNING: This will OVERWRITE your current data!${NC}"
echo ""
read -p "Type 'restore' to confirm: " confirmation

if [ "$confirmation" != "restore" ]; then
    echo "Cancelled. (You must type 'restore' exactly)"
    exit 0
fi

# Ensure containers are running
echo ""
echo -e "${YELLOW}Ensuring containers are running...${NC}"
$DOCKER_COMPOSE up -d >/dev/null 2>&1
sleep 5

# Restore database
echo ""
echo -e "${GREEN}Restoring backup...${NC}"
echo ""
echo -e "${YELLOW}1/2${NC} Restoring PostgreSQL database..."
cat "$BACKUP_DIR/${BACKUP_NAME}.sql" | $DOCKER_COMPOSE exec -T db psql -U stormcloud stormcloud >/dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Database restored"
else
    echo -e "${RED}✗${NC} Database restore failed!"
    exit 1
fi

# Restore uploads
if [ -f "$BACKUP_DIR/${BACKUP_NAME}_uploads.tar.gz" ]; then
    echo -e "${YELLOW}2/2${NC} Restoring uploads directory..."
    echo "    Destination: $UPLOADS_DIR"
    tar -xzf "$BACKUP_DIR/${BACKUP_NAME}_uploads.tar.gz" -C "$(dirname "$UPLOADS_DIR")" 2>/dev/null || true
    echo -e "${GREEN}✓${NC} Uploads restored"
else
    echo -e "${YELLOW}⚠${NC} No uploads backup found, skipping..."
fi

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}✓ Restore Complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "Your server has been restored from: ${BACKUP_NAME}"
echo ""
