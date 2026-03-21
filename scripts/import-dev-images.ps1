# Import Development Environment Images for Offline Use
# Run this on the offline machine

$ErrorActionPreference = "Stop"

$ImagesDir = "dev-images"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$InputDir = Join-Path $ProjectRoot $ImagesDir

if (-not (Test-Path $InputDir)) {
    Write-Host "Error: Images directory not found at $InputDir" -ForegroundColor Red
    Write-Host "Please copy the '$ImagesDir' folder from the online machine first." -ForegroundColor Yellow
    exit 1
}

Write-Host "=== Importing Development Images ===" -ForegroundColor Cyan
Write-Host "Source directory: $InputDir"
Write-Host ""

$TarFiles = Get-ChildItem $InputDir -Filter *.tar

if ($TarFiles.Count -eq 0) {
    Write-Host "No .tar files found in $InputDir" -ForegroundColor Red
    exit 1
}

foreach ($TarFile in $TarFiles) {
    Write-Host "Loading $($TarFile.Name)..." -ForegroundColor Yellow
    docker load -i $TarFile.FullName

    $Size = $TarFile.Length / 1MB
    Write-Host "  Loaded: $([math]::Round($Size, 2)) MB" -ForegroundColor Green
    Write-Host ""
}

Write-Host "=== Import Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Images loaded:"
docker images --format "  {{.Repository}}:{{.Tag}} ({{.Size}})" | Where-Object { $_ -match "code-server|node|python|uv|docker|nginx|deer-flow" }
Write-Host ""
Write-Host "Ready to run: docker-compose -f docker/docker-compose-dev.yaml up -d"
