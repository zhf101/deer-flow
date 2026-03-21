# DeerFlow Offline Deployment - Image Import Script (Windows PowerShell)
# Usage: .\import-images.ps1

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ImagesDir = Join-Path $ScriptDir "..\images"

Write-Host "=== DeerFlow Offline Deployment - Importing Docker Images ===" -ForegroundColor Cyan

$images = @(
    @{File="deer-flow-backend.tar"; Name="deer-flow-backend:dev"},
    @{File="deer-flow-frontend.tar"; Name="deer-flow-frontend:dev"},
    @{File="deer-flow-codeserver.tar"; Name="deer-flow-codeserver:dev"},
    @{File="nginx-alpine.tar"; Name="nginx:alpine"}
)

foreach ($img in $images) {
    $tarPath = Join-Path $ImagesDir $img.File
    if (Test-Path $tarPath) {
        Write-Host "Loading $($img.Name)..." -ForegroundColor Yellow
        docker load -i $tarPath
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] $($img.Name) loaded successfully" -ForegroundColor Green
        } else {
            Write-Host "  [ERROR] Failed to load $($img.Name)" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "  [SKIP] $($img.File) not found" -ForegroundColor DarkGray
    }
}

Write-Host "`n=== All images imported successfully! ===" -ForegroundColor Green
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | Select-String -Pattern "deer-flow|nginx"
