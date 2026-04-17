# =====================================================
#  Hotel & Event Management App Updater
# =====================================================

$projectDir   = "C:\Users\KLOUNGE\Documents\HEMS-PROJECT"
$frontendDir  = Join-Path $projectDir "react-frontend"
$backendDir   = Join-Path $projectDir "app"
$installDir   = "C:\Program Files\Hotel and Event Management App"

Write-Host "=== Hotel & Event Management App Updater ===" -ForegroundColor Cyan

# === STEP 1: Build React frontend ===
Write-Host "Building React frontend..." -ForegroundColor Yellow
Set-Location $frontendDir
npm install
npm run build

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Frontend build failed. Aborting update." -ForegroundColor Red
    exit 1
}

# === STEP 2: Remove old frontend build ===
$frontendTarget = Join-Path $installDir "react-frontend\build"
if (Test-Path $frontendTarget) {
    Write-Host "Removing old frontend build at $frontendTarget..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $frontendTarget
}

# === STEP 3: Copy new frontend build ===
Write-Host "Copying new frontend build..." -ForegroundColor Yellow
Copy-Item -Recurse -Force (Join-Path $frontendDir "build") $frontendTarget

# === STEP 4: Update backend files ===
Write-Host "Updating backend files..." -ForegroundColor Yellow
Copy-Item -Recurse -Force $backendDir (Join-Path $installDir "app")
Copy-Item -Force (Join-Path $projectDir "start.py") (Join-Path $installDir "start.py")

Write-Host "[OK] Update complete! Frontend + Backend updated successfully." -ForegroundColor Green
