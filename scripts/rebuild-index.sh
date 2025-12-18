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

# Default values
MODE="audit"
DRY_RUN=""
FORCE=""
USER_ID=""
VERBOSITY="-v 2"

# Usage message
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Rebuild the storage index from filesystem (ADR 000: Filesystem wins)"
    echo ""
    echo "Options:"
    echo "  --mode MODE       Operation mode: audit|sync|clean|full (default: audit)"
    echo "  --user-id ID      Target specific user ID (default: all users)"
    echo "  --dry-run         Preview changes without applying"
    echo "  --force           Required for clean/full modes"
    echo "  --quiet           Minimal output (-v 0)"
    echo "  --verbose         Detailed output (-v 2)"
    echo "  -h, --help        Show this help message"
    echo ""
    echo "Modes:"
    echo "  audit   - Report missing/orphaned records (default)"
    echo "  sync    - Add missing DB records from filesystem"
    echo "  clean   - Delete orphaned DB records (requires --force)"
    echo "  full    - Sync + clean (requires --force)"
    echo ""
    echo "Examples:"
    echo "  $0                              # Audit all users"
    echo "  $0 --mode sync                  # Add missing records"
    echo "  $0 --mode sync --dry-run        # Preview sync changes"
    echo "  $0 --mode clean --force         # Delete orphaned records"
    echo "  $0 --mode full --force          # Full reconciliation"
    echo "  $0 --user-id 1 --mode audit     # Audit specific user"
    echo ""
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --mode)
            MODE="$2"
            shift 2
            ;;
        --user-id)
            USER_ID="--user-id $2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        --force)
            FORCE="--force"
            shift
            ;;
        --quiet)
            VERBOSITY="-v 0"
            shift
            ;;
        --verbose)
            VERBOSITY="-v 2"
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo -e "${RED}Error: Unknown option $1${NC}"
            echo "Run '$0 --help' for usage information"
            exit 1
            ;;
    esac
done

# Validate mode
if [[ ! "$MODE" =~ ^(audit|sync|clean|full)$ ]]; then
    echo -e "${RED}Error: Invalid mode '$MODE'${NC}"
    echo "Valid modes: audit, sync, clean, full"
    exit 1
fi

# Check force requirement
if [[ "$MODE" =~ ^(clean|full)$ ]] && [[ -z "$FORCE" ]]; then
    echo -e "${RED}Error: Mode '$MODE' requires --force flag${NC}"
    echo "This prevents accidental data loss."
    exit 1
fi

# Build command
CMD="python manage.py rebuild_index --mode $MODE $USER_ID $DRY_RUN $FORCE $VERBOSITY"

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}Storm Cloud Server - Index Rebuild${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "Mode: $MODE"
[[ -n "$DRY_RUN" ]] && echo "Dry run: yes"
[[ -n "$FORCE" ]] && echo "Force: yes"
[[ -n "$USER_ID" ]] && echo "User ID: $USER_ID"
echo ""

# Execute command
$DOCKER_COMPOSE exec -T web $CMD

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ Index rebuild complete${NC}"
else
    echo ""
    echo -e "${RED}✗ Index rebuild failed${NC}"
    exit 1
fi
