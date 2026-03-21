#!/bin/bash
# Install VS Code extensions on first run (persisted in volume)

EXTENSIONS_DIR="$HOME/.local/share/code-server/extensions"
EXTENSIONS_FILE="$HOME/.extensions-installed"

# List of compatible extensions for code-server 4.96.1 (VS Code 1.96.1)
EXTENSIONS=(
    "ms-python.python@2024.0.1"
    "ms-python.debugpy@2024.0.1"
    "eamodio.gitlens"
    "esbenp.prettier-vscode"
    "dbaeumer.vscode-eslint"
    "ms-azuretools.vscode-docker"
    "redhat.vscode-yaml"
)

# Check if already installed (skip for offline mode)
if [ ! -f "$EXTENSIONS_FILE" ]; then
    echo "=== Installing VS Code Extensions ==="
    for ext in "${EXTENSIONS[@]}"; do
        echo "Installing $ext..."
        code-server --install-extension "$ext" 2>/dev/null || echo "  Warning: Failed to install $ext (will retry later)"
    done
    touch "$EXTENSIONS_FILE"
    echo "=== Extensions installed ==="
else
    echo "=== Extensions already installed (skip) ==="
fi

# Start code-server
exec code-server --bind-addr 0.0.0.0:8080 --auth none /home/coder/workspace