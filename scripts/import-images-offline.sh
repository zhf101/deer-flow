#!/bin/bash
# DeerFlow Offline Deployment - Image Import Script (Linux/Mac)
# Usage: ./import-images.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGES_DIR="$SCRIPT_DIR/../images"

echo "=== DeerFlow Offline Deployment - Importing Docker Images ==="

images=(
    "deer-flow-backend.tar:deer-flow-backend:dev"
    "deer-flow-frontend.tar:deer-flow-frontend:dev"
    "deer-flow-codeserver.tar:deer-flow-codeserver:dev"
    "nginx-alpine.tar:nginx:alpine"
)

for img in "${images[@]}"; do
    IFS=':' read -r tarfile name tag <<< "$img"
    tar_path="$IMAGES_DIR/$tarfile"
    
    if [ -f "$tar_path" ]; then
        echo -e "\033[33mLoading $name:$tag...\033[0m"
        docker load -i "$tar_path"
        echo -e "\033[32m  [OK] $name:$tag loaded successfully\033[0m"
    else
        echo -e "\033[90m  [SKIP] $tarfile not found\033[0m"
    fi
done

echo -e "\n\033[32m=== All images imported successfully! ===\033[0m"
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | grep -E "deer-flow|nginx"