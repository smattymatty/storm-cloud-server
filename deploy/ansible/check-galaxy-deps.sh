#!/bin/bash
# =============================================================================
# Ansible Galaxy Dependency Checker
# =============================================================================
# Checks if Galaxy dependencies are installed and up-to-date.
# Exit 0 if all deps are good (skip install).
# Exit 1 if deps need installation/update.
# =============================================================================

set -e

REQUIREMENTS_FILE="$(dirname "$0")/requirements.yml"
CACHE_DIR="${HOME}/.ansible"
TIMESTAMP_FILE="${CACHE_DIR}/.stormcloud_galaxy_timestamp"

# Create cache dir if it doesn't exist
mkdir -p "$CACHE_DIR"

# If requirements.yml is newer than timestamp, force reinstall
if [ -f "$TIMESTAMP_FILE" ]; then
    if [ "$REQUIREMENTS_FILE" -nt "$TIMESTAMP_FILE" ]; then
        echo "requirements.yml changed - need to reinstall"
        exit 1
    fi
else
    echo "First run - need to install"
    exit 1
fi

# Check if required roles exist
REQUIRED_ROLES=(
    "geerlingguy.docker"
    "geerlingguy.certbot"
)

for role in "${REQUIRED_ROLES[@]}"; do
    if [ ! -d "${CACHE_DIR}/roles/${role}" ]; then
        echo "Missing role: $role"
        exit 1
    fi
done

# Check if required collections exist
REQUIRED_COLLECTIONS=(
    "community.general"
    "community.postgresql"
)

for collection in "${REQUIRED_COLLECTIONS[@]}"; do
    collection_path="${CACHE_DIR}/collections/ansible_collections/${collection//./\/}"
    if [ ! -d "$collection_path" ]; then
        echo "Missing collection: $collection"
        exit 1
    fi
done

# All checks passed
echo "Galaxy dependencies up-to-date (skip install)"
exit 0
