# DeerFlow Offline Deployment - Stop Script (Windows PowerShell)
# Usage: .\stop.ps1

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Join-Path $ScriptDir ".."
$ComposeFile = Join-Path $RootDir "docker\docker-compose-dev.yaml"

Write-Host "=== Stopping DeerFlow Services ===" -ForegroundColor Cyan

Set-Location $RootDir
docker-compose -f $ComposeFile down

Write-Host "`nAll services stopped." -ForegroundColor Green
