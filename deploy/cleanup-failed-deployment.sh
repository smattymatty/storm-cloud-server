#!/bin/bash
# =============================================================================
# Storm Cloud Server - Cleanup Failed Deployment
# =============================================================================
#
# This script removes a partially-failed deployment directory that may have
# been created with incorrect ownership (root instead of stormcloud user).
#
# Usage:
#   On the remote server (as root or with sudo):
#     sudo bash cleanup-failed-deployment.sh
#
# =============================================================================

set -e

APP_USER="${APP_USER:-stormcloud}"
INSTALL_PATH="/home/${APP_USER}/storm-cloud-server"

echo "════════════════════════════════════════════════════════════════"
echo "  Storm Cloud Server - Cleanup Failed Deployment"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "This will remove: ${INSTALL_PATH}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ ERROR: This script must be run as root"
    echo "   Run: sudo bash $0"
    exit 1
fi

# Check if directory exists
if [ ! -d "$INSTALL_PATH" ]; then
    echo "✓ Directory does not exist (nothing to clean up)"
    exit 0
fi

# Show what's in the directory
echo "Current directory contents:"
ls -la "$INSTALL_PATH" || true
echo ""

# Check if it's a valid git repo
if [ -d "$INSTALL_PATH/.git" ]; then
    echo "⚠️  WARNING: Directory contains a .git folder"
    echo "   This appears to be a valid git repository."
    echo ""
    read -p "Are you sure you want to delete it? (type 'yes' to confirm): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Aborted."
        exit 1
    fi
fi

# Remove directory
echo "Removing ${INSTALL_PATH}..."
rm -rf "$INSTALL_PATH"

if [ ! -d "$INSTALL_PATH" ]; then
    echo ""
    echo "✓ Cleanup successful!"
    echo ""
    echo "Next steps:"
    echo "  1. Run 'make deploy' from your local machine"
    echo "  2. The playbook will now correctly clone the repository"
    echo ""
else
    echo ""
    echo "❌ Failed to remove directory"
    exit 1
fi

echo "════════════════════════════════════════════════════════════════"
