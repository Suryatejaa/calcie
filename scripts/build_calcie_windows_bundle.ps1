param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$Version = "0.1.0",
  [string]$Build = "1",
  [string]$Channel = "alpha"
)

$ErrorActionPreference = "Stop"

$DistRoot = Join-Path $RepoRoot "dist"
$PublishRoot = Join-Path $DistRoot "windows-publish"
$BundleRoot = Join-Path $DistRoot ("CALCIE-Windows-{0}-{1}-{2}" -f $Version, $Build, $Channel)
$BackendExe = Join-Path $DistRoot "windows-backend/dist/CalcieRuntime.exe"
$ZipPath = Join-Path $DistRoot ("CALCIE-{0}-{1}-{2}-windows.zip" -f $Version, $Build, $Channel)
$Project = Join-Path $RepoRoot "calcie_windows/CalcieTray/CalcieTray.csproj"

Write-Host "Publishing Windows tray shell..."
dotnet publish $Project -c Release -r win-x64 --self-contained true `
  -p:PublishSingleFile=true `
  -p:IncludeNativeLibrariesForSelfExtract=true `
  -o $PublishRoot

if (-not (Test-Path $BackendExe)) {
  Write-Host "Bundled backend executable not found yet. Building it now..."
  & (Join-Path $RepoRoot "scripts/build_calcie_windows_backend.ps1") -RepoRoot $RepoRoot
}

if (-not (Test-Path $BackendExe)) {
  throw "Backend executable is still missing after build. Aborting bundle creation."
}

if (Test-Path $BundleRoot) {
  Remove-Item -Recurse -Force $BundleRoot
}
New-Item -ItemType Directory -Force -Path $BundleRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $BundleRoot "backend") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $BundleRoot ".calcie/runtime") | Out-Null

Copy-Item -Recurse -Force (Join-Path $PublishRoot "*") $BundleRoot
Copy-Item -Force $BackendExe (Join-Path $BundleRoot "backend/CalcieRuntime.exe")
Copy-Item -Force (Join-Path $RepoRoot "calcie-logo.png") (Join-Path $BundleRoot "calcie-logo.png")
Copy-Item -Force (Join-Path $RepoRoot "requirements.txt") (Join-Path $BundleRoot "requirements.txt")
Copy-Item -Recurse -Force (Join-Path $RepoRoot "calcie_core") (Join-Path $BundleRoot "calcie_core")
Copy-Item -Recurse -Force (Join-Path $RepoRoot "job-hunter") (Join-Path $BundleRoot "job-hunter")
Copy-Item -Force (Join-Path $RepoRoot "calcie.py") (Join-Path $BundleRoot "calcie.py")
Copy-Item -Force (Join-Path $RepoRoot "indian-premier-league-2026-1PW.html") (Join-Path $BundleRoot "indian-premier-league-2026-1PW.html")

@"
@echo off
setlocal
cd /d %~dp0
set CALCIE_PROJECT_ROOT=%~dp0
start "" "%~dp0CalcieTray.exe"
"@ | Set-Content -Encoding ASCII (Join-Path $BundleRoot "Launch CALCIE.bat")

@"
# CALCIE Windows Beta

This portable tester bundle contains:
- CalcieTray.exe
- a bundled CalcieRuntime.exe backend

Run `Launch CALCIE.bat` or `CalcieTray.exe`.

If OneDrive, antivirus, or SmartScreen slows first launch, wait a little longer on the first run.
"@ | Set-Content -Encoding UTF8 (Join-Path $BundleRoot "README.txt")

if (Test-Path $ZipPath) {
  Remove-Item -Force $ZipPath
}
Compress-Archive -Path (Join-Path $BundleRoot "*") -DestinationPath $ZipPath

Write-Host "Built Windows tester bundle: $BundleRoot"
Write-Host "Built Windows tester zip: $ZipPath"
