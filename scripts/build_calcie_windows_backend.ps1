param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
  $OutputDir = Join-Path $RepoRoot "dist/windows-backend"
}

$BuildRoot = Join-Path $OutputDir "build"
$DistRoot = Join-Path $OutputDir "dist"
$SpecRoot = Join-Path $OutputDir "spec"
$RuntimeExe = Join-Path $DistRoot "CalcieRuntime.exe"

Write-Host "Building Windows CALCIE backend executable..."
Write-Host "Repo root: $RepoRoot"
Write-Host "Output dir: $OutputDir"

New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
New-Item -ItemType Directory -Force -Path $DistRoot | Out-Null
New-Item -ItemType Directory -Force -Path $SpecRoot | Out-Null

$pyi = @(
  "-m", "PyInstaller",
  "--noconfirm",
  "--clean",
  "--onefile",
  "--name", "CalcieRuntime",
  "--distpath", $DistRoot,
  "--workpath", $BuildRoot,
  "--specpath", $SpecRoot,
  "--paths", $RepoRoot,
  "--hidden-import", "uvicorn.logging",
  "--hidden-import", "uvicorn.loops.auto",
  "--hidden-import", "uvicorn.protocols.http.auto",
  "--hidden-import", "uvicorn.protocols.websockets.auto",
  "--hidden-import", "uvicorn.lifespan.on",
  "--hidden-import", "fastapi",
  "--hidden-import", "speech_recognition",
  "--hidden-import", "pyttsx3",
  "--hidden-import", "edge_tts",
  (Join-Path $RepoRoot "calcie_local_api/server.py")
)

& python @pyi

if (-not (Test-Path $RuntimeExe)) {
  throw "CalcieRuntime.exe was not produced. Ensure PyInstaller is installed in the active Python environment."
}

Write-Host "Built backend executable: $RuntimeExe"
