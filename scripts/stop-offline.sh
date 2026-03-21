#!/bin/bash
# DeerFlow Offline Deployment - Stop Script (Linux/Mac)
# Usage: ./stop.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker/docker-compose-dev.yaml"

echo -e "\033[36m=== Stopping DeerFlow Services ===\033[0m"

cd "$ROOT_DIR"
docker-compose -f "$COMPOSE_FILE" down

echo -e "\n\033[32mAll services stopped.\033[0m"
