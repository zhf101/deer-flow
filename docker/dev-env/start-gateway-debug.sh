#!/bin/bash
# Gateway debug startup script
# Waits for debugger to attach before starting the server

cd /app/backend

export PYTHONPATH=.

echo "[Gateway] Starting with debugpy on port 5678..."

exec uv run python -c "
import debugpy
debugpy.listen(('0.0.0.0', 5678))
print('[Gateway] debugpy waiting for attach on port 5678...')
debugpy.wait_for_client()
print('[Gateway] Debugger attached, starting server...')
import uvicorn
uvicorn.run('app.gateway.app:app', host='0.0.0.0', port=8001, reload=True)
"
