#!/bin/bash
# CasterPak Alpha - Universal Installer

echo "--- CasterPak Alpha Installation ---"


# 1. Download the project files from GitHub
echo "[1/3] Fetching deployment manifests..."
REPO_URL="https://raw.githubusercontent.com/flipmcf/casterpak/main"

# Download docker-compose.yml
curl -sSL "$REPO_URL/docker-compose.yml" -o docker-compose.yml

# Download setup.sh (making sure we overwrite any old version)
curl -sSL "$REPO_URL/setup.sh" -o setup.sh
chmod +x setup.sh

# 2. Hand off to the Setup Script for user configuration
echo "[2/3] Launching configuration wizard..."
./setup.sh

# 4. Final Launch
echo "[3/3] Starting CasterPak containers..."
if [ -f .env ]; then
    docker-compose up -d
    echo "-------------------------------------------------------"
    echo "SUCCESS: CasterPak is now running!"
    echo "Access your engine at http://localhost"
    echo "-------------------------------------------------------"
else
    echo "ERROR: Configuration failed. .env file not found."
    exit 1
fi
