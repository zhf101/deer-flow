# DeerFlow Offline Deployment Guide

This directory contains all necessary files for deploying DeerFlow in an offline environment.

## Directory Structure

```
deer-flow/
├── images/                      # Docker images (tar files)
│   ├── deer-flow-backend.tar    # Backend image
│   ├── deer-flow-frontend.tar   # Frontend image
│   ├── deer-flow-codeserver.tar # VS Code Server image
│   └── nginx-alpine.tar         # Nginx image
├── config/                      # Configuration templates
│   ├── config.yaml              # Main configuration (your setup)
│   ├── config.example.yaml      # Example configuration
│   ├── extensions_config.json   # Extensions config (your setup)
│   └── extensions_config.example.json
├── docker/                      # Docker configuration
│   ├── docker-compose-dev.yaml  # Docker Compose file
│   ├── nginx.docker.conf        # Nginx configuration
│   └── dev-env/                 # VS Code dev environment
├── scripts/                     # Deployment scripts
│   ├── import-images.ps1        # Import images (Windows)
│   ├── import-images.sh         # Import images (Linux/Mac)
│   ├── start.ps1                # Start services (Windows)
│   ├── start.sh                 # Start services (Linux/Mac)
│   ├── stop.ps1                 # Stop services (Windows)
│   └── stop.sh                  # Stop services (Linux/Mac)
└── README.md                    # This file
```

## Quick Start

### Windows (PowerShell)

```powershell
# 1. Import Docker images (first time only)
.\scripts\import-images.ps1

# 2. Start all services
.\scripts\start.ps1

# 3. Stop all services
.\scripts\stop.ps1
```

### Linux / Mac

```bash
# 1. Import Docker images (first time only)
chmod +x scripts/*.sh
./scripts/import-images.sh

# 2. Start all services
./scripts/start.sh

# 3. Stop all services
./scripts/stop.sh
```

## Access URLs

After starting the services, access the application at:

| Service | URL |
|---------|-----|
| **Main Application** | http://localhost:2026 |
| **VS Code Dev** | http://localhost:8080 |
| **LangGraph API** | http://localhost:2024 |
| **Gateway API** | http://localhost:8001 |

## Configuration

### Required Configuration

Before starting, ensure you have configured:

1. **`config.yaml`** - Main application configuration
   - Copy from `config/config.example.yaml` if not exists
   - Configure your LLM provider (OpenAI, Azure, etc.)
   - Set API keys (use `$OPENAI_API_KEY` format for env vars)

2. **`extensions_config.json`** - MCP servers and skills
   - Copy from `config/extensions_config.example.json` if not exists

### Environment Variables

You can set environment variables in your shell before starting:

```bash
# Linux/Mac
export OPENAI_API_KEY=your-key-here

# Windows PowerShell
$env:OPENAI_API_KEY = "your-key-here"
```

## Development Mode

### VS Code Server (code-server)

The offline package includes a VS Code Server running at `http://localhost:8080`. This provides a full development environment with:

- Python and Node.js pre-installed
- Pre-configured debug configurations for LangGraph
- Git integration
- Extension support

#### Debug Configuration

Press `F5` in VS Code to attach the debugger to LangGraph. The configuration is pre-set in `docker/dev-env/launch.json`.

### Attaching Debugger

1. Open VS Code at `http://localhost:8080`
2. Open the `backend` folder
3. Press `F5` to start debugging
4. The debugger will attach to the LangGraph process on port 5679

## Troubleshooting

### Port Conflicts

If ports are already in use:

```bash
# Check what's using the port
# Windows
netstat -ano | findstr :2026

# Linux/Mac
lsof -i :2026
```

### Container Logs

```bash
# View all logs
docker-compose -f docker/docker-compose-dev.yaml logs -f

# View specific service logs
docker-compose -f docker/docker-compose-dev.yaml logs -f langgraph
docker-compose -f docker/docker-compose-dev.yaml logs -f gateway
docker-compose -f docker/docker-compose-dev.yaml logs -f frontend
```

### Restart Services

```bash
# Restart all services
docker-compose -f docker/docker-compose-dev.yaml restart

# Restart specific service
docker-compose -f docker/docker-compose-dev.yaml restart langgraph
```

### Reset Everything

```bash
# Stop and remove containers
docker-compose -f docker/docker-compose-dev.yaml down

# Remove volumes (clears all data)
docker-compose -f docker/docker-compose-dev.yaml down -v
```

## File Persistence

The following directories are persisted as Docker volumes:

- `backend/.deer-flow/` - Application data (threads, memory, etc.)
- `skills/` - Custom skills directory
- `logs/` - Application logs

## Network Architecture

```
┌────────────────────────────────────────────────────────┐
│                    Nginx (2026)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ /            │  │ /api/langgraph│  │ /api/*       │ │
│  │   Frontend   │  │  LangGraph   │  │   Gateway    │ │
│  │   (3000)     │  │   (2024)     │  │   (8001)     │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│                 code-server (8080)                     │
│  VS Code Web IDE for development and debugging        │
└────────────────────────────────────────────────────────┘
```

## License

See the main LICENSE file in the original repository.
