#!/bin/bash
# Initialize workspace for DeerFlow development

set -e

echo "=== Initializing DeerFlow Workspace ==="

# Create necessary directories
mkdir -p backend/.deer-flow/threads
mkdir -p backend/.deer-flow/memory
mkdir -p logs

# Copy config files if they don't exist
if [ ! -f config.yaml ]; then
    echo "Creating config.yaml from example..."
    cp config.example.yaml config.yaml
fi

if [ ! -f extensions_config.json ]; then
    echo "Creating extensions_config.json from example..."
    cp extensions_config.example.json extensions_config.json
fi

# Install backend dependencies
echo "Installing backend dependencies..."
cd backend
uv sync
cd ..

# Install frontend dependencies
echo "Installing frontend dependencies..."
cd frontend
pnpm install
cd ..

# Copy VS Code settings
echo "Setting up VS Code configuration..."
mkdir -p .vscode
cp docker/dev-env/settings.json .vscode/
cp docker/dev-env/launch.json .vscode/
cp docker/dev-env/tasks.json .vscode/
cp docker/dev-env/extensions.json .vscode/

echo "=== Workspace initialized successfully! ==="
echo ""
echo "Next steps:"
echo "  1. Open http://localhost:8080 in your browser"
echo "  2. Configure your LLM API keys in config.yaml"
echo "  3. Use the debug configurations to start services"
