# CALCIE Windows Tray Plan

## Summary

Bring CALCIE to **Windows** as a **system tray companion** that matches the spirit of the macOS menu bar app without trying to force identical platform behavior.

The goal is:
- one shared **Python runtime core**
- one shared **local HTTP control API**
- a **Windows tray shell** instead of the macOS menu bar shell
- a staged Windows release that is useful for your early testers even before full parity

Implementation has now started in:
- `calcie_windows/`
- `calcie_windows/CalcieTray/`
- first scaffold includes:
  - tray icon
  - compact panel
  - local API client
  - typed command input
  - `vision once` submit path
  - runtime polling
  - first runtime auto-launch attempt flow
  - runtime restart action from tray + compact panel
  - hold-to-talk path wired to `Right Ctrl`
  - fallback `Ctrl+Shift+Space` voice toggle
  - update check panel using the shared `/updates/latest` backend contract
  - first CALCIE-owned player window with one reusable web surface
  - tray notifications for assistant replies and update availability

This plan assumes:
- you develop primarily on an **Apple Silicon Mac (M4)**
- your first external testers are mostly on **Windows**
- macOS and Windows should eventually ship updates in parallel

---

## Product Goal

Windows users should be able to:
- see CALCIE in the **system tray**
- open a compact command/chat panel
- use a **push-to-talk hotkey**
- review recent CALCIE responses
- trigger search, player, and safe utility actions
- receive notifications and update prompts

Windows should feel like:
- **macOS menu bar CALCIE**

not like:
- a giant always-open desktop app
- a terminal tool
- a web tab pretending to be a desktop shell

---

## Core Principle

Do **not** rebuild CALCIE’s brain per platform.

Keep these shared:
- `calcie.py`
- skill routing
- memory/profile handling
- player logic where possible
- local API contract
- update manifest format
- cloud sync/update backend

Replace only the shell:
- macOS -> Swift menu bar shell
- Windows -> native tray shell

---

## Key Decisions

- Windows surface is a **system tray app**
- Python remains the shared assistant runtime
- IPC remains **local HTTP JSON**
- Windows first release is **beta**, not full parity
- Cross-platform update flow should use the same backend model
- The Windows shell should feel native, light, and fast

---

## Windows UX Scope

### First Windows Shell Should Include

- tray icon
- open/close compact panel
- typed command input
- recent response history
- push-to-talk hotkey
- runtime state indicator
- update check/download surface
- CALCIE Player launcher
- permissions/help links
- quit CALCIE

### First Windows Shell Should Not Depend On

- full multi-page desktop app as the primary UX
- browser tabs for core assistant flows
- full parity with every macOS-only automation feature on day one

---

## Recommended Shell Technology

### Preferred

- **.NET tray app** with a native Windows UI stack

Good candidates:
- **WPF**
- **WinUI 3**

Why:
- best Windows tray/taskbar integration
- native notifications
- global hotkeys
- good installer/update ecosystem
- better long-term product feel than a browser shell

### Not Preferred For Primary Windows Shell

- Electron
- Tauri
- PyQt / PySide

These can work, but the current architecture already has a strong Python core. The Windows shell should stay focused on:
- native tray UX
- local runtime lifecycle
- minimal overhead

---

## Shared Local API Contract

Windows should use the same core endpoints the macOS shell already uses:

- `POST /command`
- `POST /voice/start`
- `POST /voice/stop`
- `POST /vision/start`
- `POST /vision/stop`
- `GET /status`
- `GET /events`
- `GET /health`
- existing profile import/status endpoints
- update-check endpoints through backend

This is important because it keeps:
- shell logic portable
- core intelligence centralized
- feature rollout easier across platforms

---

## Windows Runtime Lifecycle

The Windows tray app should:
- launch the Python runtime if not running
- health-check it
- reconnect if it restarts
- show degraded/offline state if runtime is unavailable

The runtime should remain:
- a local background process
- the owner of skills and orchestration

The shell should remain:
- the owner of tray UI
- the owner of hotkeys
- the owner of lightweight user experience

---

## Platform Feature Strategy

### Shared Early Features

- chat / typed command input
- recent response history
- search / weather / jobs / sports
- profile memory import
- update checks
- player entry points
- safe command routing

### Windows Beta Features

- tray icon
- compact panel
- push-to-talk
- notifications
- runtime start/reconnect
- player panel

### Delay Or Scope Carefully On Windows

- desktop automation parity
- app-specific launch/control differences
- screen capture permission handling
- advanced control / input injection
- full vision-monitor parity

Windows should ship a **useful subset first**, then grow.

---

## CALCIE Player On Windows

Windows should follow the same big rule:

- one CALCIE-owned player surface
- no random browser tab explosion

Target:
- a reusable CALCIE player window/panel
- shared player commands through runtime
- tray shell opens/reuses the same player surface

Windows player parity target:
- play
- pause
- resume
- next
- previous
- open player
- queue/recent item continuity

---

## Hotkey Strategy

Windows should map the macOS push-to-talk behavior into a Windows-native hold hotkey.

First version:
- configurable global hotkey
- press-and-hold to talk
- release to stop

Need to validate:
- conflicts with existing system shortcuts
- background focus behavior
- tray-app permission requirements

Do not assume the exact macOS hotkey maps cleanly.

---

## Permissions And Friction

Windows has different friction than macOS.

We should explicitly handle:
- microphone permission
- notifications
- optional screen capture permission guidance
- optional accessibility/input-control guidance if needed later

Windows onboarding should explain:
- what CALCIE needs
- what is optional
- what is only required for advanced features

---

## Packaging Plan

### Target Artifact

- `.exe` installer for Windows

Potential later options:
- MSIX
- portable zip build for testers

### Initial Recommendation

- start with a **simple Windows installer**
- include or bootstrap the Python runtime dependency cleanly
- keep install steps minimal

Windows packaging must answer:
- where the Python runtime lives
- how CALCIE starts at login
- where local data is stored
- how updates are checked/downloaded

---

## Update Strategy

Eventually macOS and Windows should share one update backend model.

Keep:
- common backend release records
- platform-specific artifacts
- channel support (`alpha`, `beta`, `stable`)

Likely release records:
- macOS artifact
- Windows artifact

Windows should eventually check:
- `platform=windows`
- same release channel logic

This allows:
- parallel releases
- per-platform rollback
- shared release notes page structure

---

## Development On M4 Mac

You are on an **M4 Mac**, so the realistic Windows dev/test flow is:

### Local Development

- keep editing shared Python/runtime code on macOS
- build Windows shell separately as Windows-targeted project code

### Sanity Testing

- use **Windows 11 ARM VM** on Apple Silicon Mac

Good for:
- tray UI sanity
- installer flow sanity
- hotkey/UI behavior
- local runtime connection checks
- update flow checks

### Real Validation

- test on real Windows machines through your friends/testers

Because VM testing will not fully replace:
- x64 dependency behavior
- real taskbar/tray edge cases
- installer/update behavior on normal Windows laptops

---

## Release Staging

### Stage 1

macOS alpha continues as the lead platform.

### Stage 2

Windows beta launches with:
- tray shell
- typed command panel
- voice hotkey
- updates
- player basics
- runtime connection

### Stage 3

Bring macOS + Windows onto a shared release cadence:
- same release notes rhythm
- same backend update model
- same product messaging
- different platform-specific known limits

---

## Acceptance Criteria For Windows Beta

- CALCIE runs without an open terminal
- CALCIE lives in the Windows tray
- user can open a compact assistant panel from the tray
- typed command flow works
- push-to-talk works
- runtime start/reconnect works
- update checks work
- CALCIE Player opens and reuses one player surface
- at least a meaningful subset of shared skills works on Windows

---

## Risks

### 1. Platform Drift

If macOS and Windows shells evolve separately without a shared API discipline, CALCIE will split into two products.

Mitigation:
- keep runtime contract stable
- keep shell responsibilities narrow

### 2. Overreaching On Parity

If we try to port every macOS automation feature first, Windows launch will stall.

Mitigation:
- define a Windows beta subset
- ship useful core behavior first

### 3. Weak Testing Confidence

Windows ARM VM on M4 is helpful, but not enough alone.

Mitigation:
- use real Windows testers early

### 4. Packaging Complexity

Bundling runtime, shell, installer, and updates on Windows can get messy fast.

Mitigation:
- keep installer simple first
- solve runtime ownership before fancy packaging

---

## Recommended Implementation Order

1. Define **CALCIE Core** features shared across macOS and Windows
2. Freeze the **local HTTP contract** as the platform boundary
3. Create a Windows tray-shell prototype
4. Validate command flow + runtime lifecycle in Windows VM
5. Add player panel integration
6. Add update checks
7. Ship to real Windows testers
8. Close the biggest platform gaps
9. Move macOS + Windows onto shared release cadence

---

## Immediate Next Steps

1. Create a Windows-specific shell repo/folder boundary
2. Decide exact Windows native UI stack
3. Define Windows beta feature subset
4. Define installer/runtime ownership model
5. Build tray shell prototype before expanding automation scope

---

## Final Position

Yes, CALCIE should live in the **Windows tray**, just like it lives in the **macOS menu bar**.

But Windows should launch as:
- a focused **tray-shell beta**
- powered by the same Python brain
- tested first in VM, then on real Windows machines

That gives you the fastest path to:
- real Windows testers
- shared product momentum
- future parallel macOS + Windows releases
