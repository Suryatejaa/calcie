# CALCIE Windows Tray Shell

This directory contains the first Windows shell scaffold for CALCIE.

Current scope:
- system tray icon
- compact command window
- runtime health/status polling
- runtime auto-launch attempts when the local API is offline
- runtime restart action from the tray shell
- hold-to-talk hotkey: `Right Ctrl`
- fallback voice toggle hotkey: `Ctrl+Shift+Space`
- update check UI using the shared CALCIE cloud release manifest
- first CALCIE-owned player window entry point
- tray balloon notifications for assistant responses and update availability
- recent event list
- typed command input
- voice start/stop buttons
- shared local HTTP API contract with the macOS shell

This is the **start of the Windows beta surface**, not full parity yet.

## Architecture

Windows keeps the same core split as macOS:

- Python runtime: `calcie.py`
- Local IPC/API: `calcie_local_api/`
- Native shell: `calcie_windows/`

The shell is intentionally thin:
- tray UX
- lightweight panel
- runtime lifecycle/status display
- local API calls

## Project

Main project:

```text
calcie_windows/CalcieTray/CalcieTray.csproj
```

## Build notes

This project targets **WPF on Windows** and should be built on a Windows machine.

Recommended environments:
- Visual Studio 2022
- .NET 8 SDK on Windows

Example from Windows PowerShell:

```powershell
cd calcie_windows/CalcieTray
dotnet build
dotnet run
```

## Runtime expectation

The Windows shell expects the local CALCIE API to be reachable at:

```text
http://127.0.0.1:8765
```

The shell now attempts to launch the runtime automatically when the API is offline.

Launch candidates:

```text
py -3 -m calcie_local_api.server
python -m calcie_local_api.server
python3 -m calcie_local_api.server
```

That means Python should be available on the Windows machine and the shell should know where the Jarvis repo/runtime lives.

Recommended environment variable:

```powershell
$env:CALCIE_PROJECT_ROOT="C:\path\to\Jarvis"
```

Manual runtime command if needed:

```bash
python3 -m calcie_local_api.server
```

Current limitation:
- this is still a repo-backed beta scaffold
- the runtime launcher expects the Jarvis project root, not a fully bundled consumer runtime yet
- push-to-talk now prefers **hold Right Ctrl**, but still needs real Windows validation across keyboards and international layouts
- `Ctrl+Shift+Space` remains as a fallback toggle path
- update UI currently opens download/release-notes URLs in the browser instead of performing in-app install
- the first player milestone is bootstrap-only:
  - one Windows-owned player window
  - one reusable web surface
  - YouTube / YouTube Music home entry points
  - not yet full runtime-driven media parity

## Near-term next steps

1. Build and test on Windows 11
2. Add stronger reconnect/backoff polish
3. Validate and tune push-to-talk behavior on real Windows hardware
4. Add richer update/install flow
5. Connect player actions more deeply with runtime/media commands
