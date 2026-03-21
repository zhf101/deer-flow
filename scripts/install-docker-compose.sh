#!/bin/bash
# Install Docker Compose for offline environment (RedHat 8.8)
# Usage: ./install-docker-compose.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_BIN="$SCRIPT_DIR/docker-compose"
TARGET_DIR="/usr/local/bin"

echo "=== Installing Docker Compose (Offline) ==="

# Check if docker-compose binary exists
if [ ! -f "$COMPOSE_BIN" ]; then
    echo "[ERROR] docker-compose binary not found in $SCRIPT_DIR"
    exit 1
fi

# Check Docker version
echo "Checking Docker version..."
docker --version

# Install docker-compose
echo "Installing docker-compose to $TARGET_DIR..."
sudo cp "$COMPOSE_BIN" "$TARGET_DIR/docker-compose"
sudo chmod +x "$TARGET_DIR/docker-compose"

# Verify installation
echo "Verifying installation..."
docker-compose --version

# Create symlink for 'docker compose' plugin style (optional)
echo "Creating symlink for 'docker compose' command..."
sudo mkdir -p /usr/libexec/docker/cli-plugins
sudo ln -sf "$TARGET_DIR/docker-compose" /usr/libexec/docker/cli-plugins/docker-compose

echo ""
echo "=== Installation Complete ==="
echo "You can now use:"
echo "  docker-compose up -d"
echo "  # or"
echo "  docker compose up -d"
