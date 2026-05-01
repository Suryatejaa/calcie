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
$AppRoot = Join-Path $BundleRoot "app"
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
New-Item -ItemType Directory -Force -Path $AppRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $AppRoot "backend") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $AppRoot ".calcie/runtime") | Out-Null

function Copy-OptionalItem {
  param(
    [string]$SourcePath,
    [string]$DestinationPath
  )

  if (Test-Path $SourcePath) {
    Copy-Item -Recurse -Force $SourcePath $DestinationPath
  }
  else {
    Write-Host "Skipping optional bundle asset: $SourcePath"
  }
}

function Copy-PublishPayload {
  param(
    [string]$SourceRoot,
    [string]$DestinationRoot
  )

  $allowedFiles = @(
    "CalcieTray.exe",
    "WebView2Loader.dll"
  )

  foreach ($fileName in $allowedFiles) {
    $sourcePath = Join-Path $SourceRoot $fileName
    if (Test-Path $sourcePath) {
      $targetName = if ($fileName -eq "CalcieTray.exe") { "CALCIE.exe" } else { $fileName }
      Copy-Item -Force $sourcePath (Join-Path $DestinationRoot $targetName)
    }
  }
}

Copy-PublishPayload -SourceRoot $PublishRoot -DestinationRoot $BundleRoot
Copy-Item -Force $BackendExe (Join-Path $AppRoot "backend/CalcieRuntime.exe")
Copy-OptionalItem (Join-Path $RepoRoot "calcie-logo.png") (Join-Path $AppRoot "calcie-logo.png")
Copy-OptionalItem (Join-Path $RepoRoot ".env.example") (Join-Path $AppRoot ".env.example")
Copy-Item -Recurse -Force (Join-Path $RepoRoot "calcie_core") (Join-Path $AppRoot "calcie_core")
Copy-Item -Force (Join-Path $RepoRoot "calcie.py") (Join-Path $AppRoot "calcie.py")
Copy-OptionalItem (Join-Path $RepoRoot "indian-premier-league-2026-1PW.html") (Join-Path $AppRoot "indian-premier-league-2026-1PW.html")

@"
@echo off
setlocal
cd /d %~dp0
set CALCIE_PROJECT_ROOT=%~dp0app
start "" "%~dp0CALCIE.exe"
"@ | Set-Content -Encoding ASCII (Join-Path $BundleRoot "Launch CALCIE.bat")

@"
# CALCIE Windows Beta

This portable tester bundle contains:
- CALCIE.exe
- an internal bundled local runtime under `app\backend`

Run `Launch CALCIE.bat`.

If SmartScreen warns, choose More info -> Run anyway for this beta build.
If OneDrive, antivirus, or SmartScreen slows first launch, wait a little longer on the first run.
"@ | Set-Content -Encoding UTF8 (Join-Path $BundleRoot "README.txt")

if (Test-Path $ZipPath) {
  Remove-Item -Force $ZipPath
}
Compress-Archive -Path (Join-Path $BundleRoot "*") -DestinationPath $ZipPath

Write-Host "Built Windows tester bundle: $BundleRoot"
Write-Host "Built Windows tester zip: $ZipPath"
