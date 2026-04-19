# CALCIE macOS Menu Bar Shell

This directory contains the first native macOS shell for CALCIE.

## What it does

- menu bar status item
- hold-to-talk hotkey: `Right Option`
- launch-at-login toggle for packaged `CALCIE.app`
- typed command entry
- start/stop voice capture
- start/stop vision monitor
- recent runtime events
- native permission status checks for:
  - microphone
  - accessibility
  - screen recording
  - notifications
- permission shortcuts
- runtime identity details (pid, instance id, project root)
- restart runtime action from the shell
- compact menu bar popover with a separate floating `Advanced Options` panel
- launches the local Python CALCIE runtime when needed

## Runtime dependency

The Swift shell talks to CALCIE through the local HTTP control API:

- Python entrypoint: `python3 -m calcie_local_api.server`
- default host: `127.0.0.1`
- default port: `8765`

The shell tries to start that runtime automatically if it is offline.

Important:
- `python3 -m calcie_local_api.server` must be run from the **Jarvis repo root**, not from inside `calcie_macos`
- easiest option:

```bash
./scripts/run_calcie_local_api.sh
```

## Open in Xcode

Open `calcie_macos/Package.swift` in Xcode.

## Run from terminal

```bash
cd calcie_macos
swift run
```

If the menu bar app cannot find the project root correctly, set:

```bash
export CALCIE_PROJECT_ROOT="/Volumes/D-Drive/Projects/Jarvis"
```

## Build as `CALCIE.app`

Package the shell into a real app bundle:

```bash
./scripts/build_calcie_macos_app.sh
```

Output:

```text
dist/CALCIE.app
```

You can move that app bundle into `~/Applications` or `/Applications`.

## Install into `~/Applications`

To build and install the app in one step:

```bash
./scripts/install_calcie_macos_app.sh
```

This will:
- rebuild the shell bundle
- copy `CALCIE.app` into `~/Applications`
- remove quarantine metadata when possible
- launch the app by default

To install without auto-launching:

```bash
CALCIE_OPEN_AFTER_INSTALL=0 ./scripts/install_calcie_macos_app.sh
```

Current limitation:

- the app bundle still points back to your local Jarvis repo for the Python runtime and config
- it is a local packaging step, not yet a fully self-contained distributed desktop app
- if CALCIE is built with ad-hoc signing, macOS privacy permissions can reset after reinstall
- the app is still repo-backed, but now includes bundle build metadata so CALCIE can explain how it was packaged

## Stable Code Signing

To keep macOS privacy permissions more stable across reinstalls, build CALCIE with a real signing identity instead of ad-hoc signing.

Recommended env:

```bash
export CALCIE_CODESIGN_IDENTITY="Apple Development: Your Name (TEAMID)"
```

Then rebuild/install:

```bash
./scripts/install_calcie_macos_app.sh
```

Notes:
- `security find-identity -v -p codesigning` shows which identities are available
- if no valid identities are installed, the build falls back to ad-hoc signing
- ad-hoc signing is the main reason microphone/notification permissions can reset after reinstall
- easiest helper:

```bash
./scripts/check_calcie_codesign.sh
```

- setup guide:
  - [/Volumes/D-Drive/Projects/Jarvis/CALCIE_CODESIGN_SETUP.md](/Volumes/D-Drive/Projects/Jarvis/CALCIE_CODESIGN_SETUP.md)

## Launch At Login

The shell now exposes a **Launch CALCIE at Login** toggle in the menu.

Notes:
- this works best when `CALCIE.app` is installed in `~/Applications` or `/Applications`
- the toggle uses macOS app-service registration, so packaged app identity matters
- if macOS requires approval, the shell will show that in the startup message

## Notes

- This is a macOS-first shell, not a replacement for the Python runtime.
- Terminal mode still remains the best developer/debug surface.
- The packaged app is still repo-backed for the Python runtime and config.
