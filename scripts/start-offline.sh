#!/bin/bash
# DeerFlow Offline Deployment - One-Click Start Script (Linux/Mac)
# Usage: ./start.sh [--skip-import] [--dev]

set -e

SKIP_IMPORT=false
DEV_MODE=false

for arg in "$@"; do
    case $arg in
        --skip-import) SKIP_IMPORT=true ;;
        --dev) DEV_MODE=true ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "\033[36m=== DeerFlow Offline Deployment ===\033[0m"

# Step 1: Check and import Docker images if needed
echo -e "\n\033[33m[Step 1/4] Checking Docker images...\033[0m"

required_images=("deer-flow-backend:dev" "deer-flow-frontend:dev" "nginx:alpine")
missing_images=()
for img in "${required_images[@]}"; do
    if ! docker image inspect "$img" &>/dev/null; then
        missing_images+=("$img")
    fi
done

if [ ${#missing_images[@]} -eq 0 ]; then
    echo -e "\033[32m  All required images already exist, skipping import\033[0m"
elif [ "$SKIP_IMPORT" = true ]; then
    echo -e "\033[31m  [ERROR] Missing images: ${missing_images[*]}\033[0m"
    echo -e "\033[33m  Run './scripts/import-images.sh' first or remove --skip-import flag\033[0m"
    exit 1
else
    echo -e "\033[33m  Missing images: ${missing_images[*]}\033[0m"
    echo -e "\033[33m  Importing Docker images...\033[0m"
    chmod +x "$SCRIPT_DIR/import-images.sh"
    "$SCRIPT_DIR/import-images.sh"
fi

# Step 2: Check configuration files
echo -e "\n\033[33m[Step 2/4] Checking configuration files...\033[0m"

config_yaml="$ROOT_DIR/config.yaml"
config_example="$ROOT_DIR/config.example.yaml"
if [ ! -f "$config_yaml" ]; then
    if [ -f "$config_example" ]; then
        cp "$config_example" "$config_yaml"
        echo -e "\033[32m  Created config.yaml from example\033[0m"
    else
        echo -e "\033[33m  [WARN] config.yaml not found. Please create it manually.\033[0m"
    fi
else
    echo -e "\033[32m  config.yaml exists\033[0m"
fi

ext_config="$ROOT_DIR/extensions_config.json"
ext_example="$ROOT_DIR/extensions_config.example.json"
if [ ! -f "$ext_config" ]; then
    if [ -f "$ext_example" ]; then
        cp "$ext_example" "$ext_config"
        echo -e "\033[32m  Created extensions_config.json from example\033[0m"
    else
        echo -e "\033[33m  [WARN] extensions_config.json not found. Please create it manually.\033[0m"
    fi
else
    echo -e "\033[32m  extensions_config.json exists\033[0m"
fi

# Create .env file if not exists
env_file="$ROOT_DIR/.env"
env_example="$ROOT_DIR/.env.example"
if [ ! -f "$env_file" ] && [ -f "$env_example" ]; then
    cp "$env_example" "$env_file"
    echo -e "\033[32m  Created .env from example\033[0m"
fi

# Step 3: Start Docker Compose
echo -e "\n\033[33m[Step 3/4] Starting Docker services...\033[0m"
DOCKER_DIR="$ROOT_DIR/docker"
COMPOSE_FILE="$DOCKER_DIR/docker-compose-dev.yaml"

# Copy nginx config
NGINX_SRC="$DOCKER_DIR/nginx.docker.conf"
NGINX_DST="$DOCKER_DIR/nginx/nginx.conf"
if [ -f "$NGINX_SRC" ]; then
    mkdir -p "$DOCKER_DIR/nginx"
    cp "$NGINX_SRC" "$NGINX_DST"
    echo -e "\033[32m  Copied nginx.docker.conf to nginx.conf\033[0m"
fi

cd "$ROOT_DIR"

if [ "$DEV_MODE" = true ]; then
    export DEER_FLOW_DEV_MODE=true
fi

docker-compose -f "$COMPOSE_FILE" up -d

echo -e "\n\033[32m[Step 4/4] Services started successfully!\033[0m"

# Show service status
echo -e "\n\033[36m=== Service Status ===\033[0m"
docker-compose -f "$COMPOSE_FILE" ps

echo -e "\n\033[36m=== Access URLs ===\033[0m"
echo -e "  Main Application:  \033[37mhttp://localhost:2026\033[0m"
echo -e "  VS Code Dev:       \033[37mhttp://localhost:8080\033[0m"
echo -e "  LangGraph API:     \033[37mhttp://localhost:2024\033[0m"
echo -e "  Gateway API:       \033[37mhttp://localhost:8001\033[0m"

echo -e "\n\033[36m=== Logs ===\033[0m"
echo -e "\033[90m  View logs:  docker-compose -f $COMPOSE_FILE logs -f\033[0m"
echo -e "\033[90m  Stop all:   docker-compose -f $COMPOSE_FILE down\033[0m"
