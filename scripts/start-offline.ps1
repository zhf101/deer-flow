# DeerFlow Offline Deployment - One-Click Start Script (Windows PowerShell)
# Usage: .\start.ps1

param(
    [switch]$SkipImport,
    [switch]$Dev
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Join-Path $ScriptDir ".."

Write-Host "=== DeerFlow Offline Deployment ===" -ForegroundColor Cyan

# Step 1: Check and import Docker images if needed
Write-Host "`n[Step 1/4] Checking Docker images..." -ForegroundColor Yellow

$requiredImages = @("deer-flow-backend:dev", "deer-flow-frontend:dev", "nginx:alpine")
$missingImages = @()
foreach ($img in $requiredImages) {
    $exists = docker image inspect $img 2>$null
    if (-not $?) {
        $missingImages += $img
    }
}

if ($missingImages.Count -eq 0) {
    Write-Host "  All required images already exist, skipping import" -ForegroundColor Green
} elseif ($SkipImport) {
    Write-Host "  [ERROR] Missing images: $($missingImages -join ', ')" -ForegroundColor Red
    Write-Host "  Run '.\scripts\import-images.ps1' first or remove -SkipImport flag" -ForegroundColor Yellow
    exit 1
} else {
    Write-Host "  Missing images: $($missingImages -join ', ')" -ForegroundColor Yellow
    Write-Host "  Importing Docker images..." -ForegroundColor Yellow
    & "$ScriptDir\import-images.ps1"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to import images" -ForegroundColor Red
        exit 1
    }
}

# Step 2: Check configuration files
Write-Host "`n[Step 2/4] Checking configuration files..." -ForegroundColor Yellow

$configYaml = Join-Path $RootDir "config.yaml"
$configExample = Join-Path $RootDir "config.example.yaml"
if (-not (Test-Path $configYaml)) {
    if (Test-Path $configExample) {
        Copy-Item $configExample $configYaml
        Write-Host "  Created config.yaml from example" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] config.yaml not found. Please create it manually." -ForegroundColor Yellow
    }
} else {
    Write-Host "  config.yaml exists" -ForegroundColor Green
}

$extConfig = Join-Path $RootDir "extensions_config.json"
$extConfigExample = Join-Path $RootDir "extensions_config.example.json"
if (-not (Test-Path $extConfig)) {
    if (Test-Path $extConfigExample) {
        Copy-Item $extConfigExample $extConfig
        Write-Host "  Created extensions_config.json from example" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] extensions_config.json not found. Please create it manually." -ForegroundColor Yellow
    }
} else {
    Write-Host "  extensions_config.json exists" -ForegroundColor Green
}

# Create .env file if not exists
$envFile = Join-Path $RootDir ".env"
$envExample = Join-Path $RootDir ".env.example"
if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Write-Host "  Created .env from example" -ForegroundColor Green
    }
}

# Step 3: Start Docker Compose
Write-Host "`n[Step 3/4] Starting Docker services..." -ForegroundColor Yellow
$DockerDir = Join-Path $RootDir "docker"
$ComposeFile = Join-Path $DockerDir "docker-compose-dev.yaml"

# Copy nginx config
$NginxSrc = Join-Path $DockerDir "nginx.docker.conf"
$NginxDst = Join-Path $DockerDir "nginx\nginx.conf"
if (Test-Path $NginxSrc) {
    $NginxDir = Join-Path $DockerDir "nginx"
    if (-not (Test-Path $NginxDir)) {
        New-Item -ItemType Directory -Path $NginxDir -Force | Out-Null
    }
    Copy-Item $NginxSrc $NginxDst -Force
    Write-Host "  Copied nginx.docker.conf to nginx.conf" -ForegroundColor Green
}

# Set environment variable for dev mode
if ($Dev) {
    $env:DEER_FLOW_DEV_MODE = "true"
}

Set-Location $RootDir
docker-compose -f $ComposeFile up -d

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n[Step 4/4] Services started successfully!" -ForegroundColor Green
} else {
    Write-Host "`n[Step 4/4] Failed to start services" -ForegroundColor Red
    exit 1
}

# Show service status
Write-Host "`n=== Service Status ===" -ForegroundColor Cyan
docker-compose -f $ComposeFile ps

Write-Host "`n=== Access URLs ===" -ForegroundColor Cyan
Write-Host "  Main Application:  http://localhost:2026" -ForegroundColor White
Write-Host "  VS Code Dev:       http://localhost:8080" -ForegroundColor White
Write-Host "  LangGraph API:     http://localhost:2024" -ForegroundColor White
Write-Host "  Gateway API:       http://localhost:8001" -ForegroundColor White

Write-Host "`n=== Logs ===" -ForegroundColor Cyan
Write-Host "  View logs:  docker-compose -f $ComposeFile logs -f" -ForegroundColor DarkGray
Write-Host "  Stop all:   docker-compose -f $ComposeFile down" -ForegroundColor DarkGray
