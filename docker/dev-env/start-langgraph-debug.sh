#!/bin/bash
# LangGraph debug startup script
# Waits for debugger to attach before starting the server

cd /app/backend

export PYTHONPATH=.

echo "[LangGraph] Starting with debugpy on port 5679..."

exec uv run python -c "
import debugpy
debugpy.listen(('0.0.0.0', 5679))
print('[LangGraph] debugpy waiting for attach on port 5679...')
debugpy.wait_for_client()
print('[LangGraph] Debugger attached, starting server...')
import subprocess
subprocess.run(['uv', 'run', 'langgraph', 'dev', '--no-browser', '--allow-blocking', '--host', '0.0.0.0', '--port', '2024'])
"
