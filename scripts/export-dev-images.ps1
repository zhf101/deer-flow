# Export Development Environment Images for Offline Use
# Run this on a machine with internet access

$ErrorActionPreference = "Stop"

$ImagesDir = "dev-images"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

# Create output directory
$OutputDir = Join-Path $ProjectRoot $ImagesDir
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

Write-Host "=== Exporting Base Images ===" -ForegroundColor Cyan

# Base images (pulled from registry)
$BaseImages = @(
    @{ Name = "codercom/code-server:4.96.1"; File = "codeserver-base.tar" },
    @{ Name = "node:22-slim"; File = "node-slim.tar" },
    @{ Name = "python:3.12-slim"; File = "python-slim.tar" },
    @{ Name = "ghcr.io/astral-sh/uv:0.7.20"; File = "uv.tar" },
    @{ Name = "docker:cli"; File = "docker-cli.tar" },
    @{ Name = "nginx:alpine"; File = "nginx-alpine.tar" }
)

foreach ($Image in $BaseImages) {
    $ImagePath = Join-Path $OutputDir $Image.File

    Write-Host "Pulling $($Image.Name)..." -ForegroundColor Yellow
    docker pull $Image.Name

    Write-Host "Exporting to $($Image.File)..." -ForegroundColor Yellow
    docker save -o $ImagePath $Image.Name

    $Size = (Get-Item $ImagePath).Length / 1MB
    Write-Host "  Size: $([math]::Round($Size, 2)) MB" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Building DeerFlow Images ===" -ForegroundColor Cyan

Set-Location $ProjectRoot
docker-compose -f docker/docker-compose-build.yaml build --no-cache

Write-Host ""
Write-Host "=== Exporting Built Images ===" -ForegroundColor Cyan

# Built images
$BuiltImages = @(
    @{ Name = "deer-flow-frontend:dev"; File = "deer-flow-frontend.tar" },
    @{ Name = "deer-flow-backend:dev"; File = "deer-flow-backend.tar" },
    @{ Name = "deer-flow-codeserver:dev"; File = "deer-flow-codeserver.tar" },
    @{ Name = "deer-flow-provisioner:dev"; File = "deer-flow-provisioner.tar" }
)

foreach ($Image in $BuiltImages) {
    $ImagePath = Join-Path $OutputDir $Image.File

    if (docker image inspect $Image.Name 2>$null) {
        Write-Host "Exporting $($Image.Name)..." -ForegroundColor Yellow
        docker save -o $ImagePath $Image.Name

        $Size = (Get-Item $ImagePath).Length / 1MB
        Write-Host "  Size: $([math]::Round($Size, 2)) MB" -ForegroundColor Green
    }
    else {
        Write-Host "Image $($Image.Name) not found, skipping..." -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "=== Export Complete ===" -ForegroundColor Green
$TotalSize = (Get-ChildItem $OutputDir -Filter *.tar | Measure-Object -Property Length -Sum).Sum / 1GB
Write-Host "Total size: $([math]::Round($TotalSize, 2)) GB" -ForegroundColor Cyan
Write-Host ""
Write-Host "Copy the '$ImagesDir' folder to your offline machine and run:"
Write-Host "  .\scripts\import-dev-images.ps1" -ForegroundColor Yellow