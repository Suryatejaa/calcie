# CALCIE macOS System-App Transition Plan

## Status Snapshot

Overall status: **Partially complete**

This plan is no longer just a proposal. A large part of the first macOS system-app transition has already been implemented.

### Completed

- [x] Python runtime remains the main CALCIE brain
- [x] Native macOS shell exists in `calcie_macos/`
- [x] Menu bar app exists and runs
- [x] Local HTTP IPC exists in `calcie_local_api/`
- [x] Runtime state model exists (`idle`, `listening`, `thinking`, `speaking`, `vision_monitoring`, `error`, etc.)
- [x] Shell can send typed commands to runtime
- [x] Shell can start/stop voice capture
- [x] Shell can start/stop vision monitor
- [x] Runtime event feed exists and is shown in shell
- [x] Packaged `CALCIE.app` path exists
- [x] Push-to-talk exists via shell hotkey flow

### Partially Complete

- [~] Permission flow now includes native shell-side checks and request actions, but reinstall persistence still depends on stable signing
- [~] Background runtime lifecycle now includes runtime identity + restart controls, but is still repo-backed and not fully self-contained
- [~] Menu bar UX now has a compact quick-control popover plus a floating advanced panel, but still has room for final polish
- [~] Packaged app now exposes bundle metadata/signing diagnostics, but runtime bundling is not complete

### Not Complete Yet

- [x] Launch at login
- [ ] Fully self-contained app bundle
- [ ] Strong native permission-state detection and onboarding
- [ ] Final shell/runtime hardening for production-style desktop use

---

## Remaining Work Before CALCIE Player

We should finish these before starting `CALCIE Player`.

### 1. Launch At Login

Status:
- Done in the shell UI for packaged `CALCIE.app`

Goal:
- CALCIE starts like a real desktop companion without needing manual launch every session.

Definition of done:
- [x] user can enable launch-at-login from the menu bar shell
- [~] `CALCIE.app` appears and starts reliably after login

### 2. Permission Productization

Status:
- Native shell-side permission detection is now in place for microphone, accessibility, screen recording, and notifications
- Shell buttons can now trigger native permission requests for microphone and notifications
- Remaining blocker is stable signing so permissions persist across reinstalls

Goal:
- the shell shows trustworthy permission state for `CALCIE.app`, not just generic checklist guidance.

Definition of done:
- [x] app can detect missing microphone/accessibility/screen recording permission more reliably
- [~] onboarding path is clear for packaged app usage

### 3. Runtime Ownership Hardening

Status:
- Runtime now exposes identity metadata (`pid`, instance id, started-at time, project root)
- The shell can detect a mismatched runtime root and request a runtime restart
- Remaining work is reducing stale-process confusion even further and making recovery feel more automatic

Goal:
- the shell owns runtime lifecycle more cleanly.

Definition of done:
- [x] shell reliably starts runtime if missing
- [~] shell recovers better from runtime death/offline state
- [~] stale runtime / stale app version confusion is reduced

### 4. Packaged App Hardening

Status:
- Packaged app now carries build metadata (`project_root`, build config, signing style, signing identity, build time)
- Advanced Options shows bundle location, build/signing summary, and warnings for repo-root/signing problems
- Remaining work is reducing repo-backed assumptions and moving closer to a self-contained app

Goal:
- `CALCIE.app` behaves more like a real product and less like a thin repo launcher.

Definition of done:
- [~] repo-backed assumptions are reduced where possible
- [x] packaged app workflow is documented and predictable

### 5. Final macOS Shell Polish

Status:
- Compact quick-control popover is in place
- Advanced Options now holds the heavier runtime/settings panels
- Remaining work is mostly interaction refinement and visual cleanup

Goal:
- the menu bar app is stable enough to be CALCIE’s default desktop face.

Definition of done:
- [x] hotkey flow is reliable
- [x] status updates are trustworthy
- [x] noisy local API logs stay hidden by default
- [~] core menu actions feel consistent

---

## Exit Criteria For This Plan

We should mark this macOS system-app transition as complete only when:

- [x] CALCIE can be used meaningfully without terminal or Xcode
- [x] `CALCIE.app` is the normal desktop entrypoint
- [ ] hotkey invocation is reliable enough for daily use
- [ ] permissions are understandable for packaged app users
- [ ] runtime lifecycle is stable enough that the app does not feel fragile
- [ ] remaining work is polish, not foundational architecture

---

## Recommended Execution Order

1. Packaged app hardening
2. Final shell polish
3. Stable signing workflow
   - helper script now exists: `./scripts/check_calcie_codesign.sh`
   - setup doc now exists: `CALCIE_CODESIGN_SETUP.md`
4. Mark this plan complete
5. Start `CALCIE_PLAYER_PLAN.md`

## Summary

Move CALCIE from a terminal-first assistant into a **macOS-native background companion** while keeping the terminal as the **developer/debug surface**. The first release should feel more like Jarvis through:
- a **menu bar app**
- a **global push-to-talk / invoke hotkey**
- **system notifications**
- a **background assistant runtime**
- integration with existing CALCIE skills for app control, vision, search, and desktop actions

This phase does **not** replace the current Python runtime. It wraps and stabilizes it behind a native macOS control layer.

## Implementation Changes

### 1. Split CALCIE into Runtime Core + macOS Shell

- Keep the current Python assistant runtime as the **core engine** for:
  - routing
  - skills
  - LLM/TTS/STT logic
  - persistence
  - sync
  - screen vision loop
- Introduce a **macOS shell app** as the user-facing layer.
- The shell app should not duplicate CALCIE logic. It should:
  - launch/monitor the Python runtime
  - send commands to it
  - receive state/events from it
  - expose user controls through native macOS surfaces

### 2. Choose Native macOS Shell: Swift Menu Bar App

- Build the first system-app surface as a **Swift menu bar application**, not Electron/Tauri.
- Reasons:
  - best fit for macOS-first
  - stronger menu bar + hotkey + notification integration
  - lower resource overhead
  - closer to “Jarvis” feel than a browser-style shell
- The Swift app should provide:
  - menu bar status icon
  - microphone / listening indicator
  - quick actions menu
  - start/stop screen vision
  - open terminal logs/debug
  - recent command/result summary
  - hotkey registration

### 3. Define Local IPC Between Swift Shell and Python Runtime

- Add a **local IPC boundary** between the macOS shell and `calcie.py`.
- Recommended contract:
  - Python runtime runs as a **local HTTP or Unix-socket control server**
  - Swift shell sends commands like:
    - `submit_text`
    - `start_listening`
    - `stop_listening`
    - `vision_start`
    - `vision_stop`
    - `get_status`
    - `get_recent_events`
  - Python runtime emits state like:
    - `idle`
    - `listening`
    - `thinking`
    - `speaking`
    - `vision_running`
    - `error`
- Decision:
  - use **local HTTP JSON control endpoints** first for simplicity and debuggability
  - keep request/response schema small and explicit
- Initial API surface:
  - `POST /command`
  - `POST /voice/start`
  - `POST /voice/stop`
  - `POST /vision/start`
  - `POST /vision/stop`
  - `GET /status`
  - `GET /events`
  - `GET /health`

### 4. Keep Terminal as Control Plane, Not Main UX

- Terminal remains useful for:
  - route trace
  - logs
  - skill debugging
  - proposal/diff workflows
  - dev-only commands
- End-user flows should move to the shell app:
  - hotkey -> speak/type -> response
  - menu bar quick actions
  - native notifications
- `calcie.py` should continue to run standalone in terminal for development, but the new shell path should become the default “assistant mode.”

### 5. Add Background Runtime Lifecycle

- CALCIE needs a persistent background process independent of an open terminal window.
- The macOS shell should be responsible for:
  - starting the Python runtime if not running
  - health-checking it
  - restarting it if it crashes
- The runtime should expose:
  - startup-ready state
  - configuration summary
  - current active skills
  - permission-related failure messages
- Do not turn CALCIE into a completely autonomous always-acting agent yet.
- Default lifecycle:
  - menu bar app launches at login
  - Python runtime starts on demand or at login based on setting
  - shell shows degraded state if runtime is offline

### 6. Define First-Class Assistant States

- Add a stable runtime state model for UI display:
  - `offline`
  - `starting`
  - `idle`
  - `listening`
  - `thinking`
  - `speaking`
  - `executing`
  - `vision_monitoring`
  - `needs_permission`
  - `error`
- These states must be queryable through `/status`.
- Menu bar icon and menu labels should be driven by this state, not inferred ad hoc.

### 7. Global Hotkey and Invocation Flow

- First non-terminal invocation should be **push-to-talk**, not always-on wake-word as the primary UX.
- Hotkey behavior:
  - single shortcut press: start voice capture
  - release or second press: stop capture and submit
  - fallback action: open quick input popover if mic unavailable
- Keep wake-word support available, but do not make it the core desktop invocation method because:
  - battery
  - permissions
  - reliability
  - constant mic indicator concerns
- Shell app should own hotkey registration and signal Python runtime to begin/stop listening.

### 8. Add Menu Bar UX Scope

- First menu bar version should include:
  - current CALCIE state
  - “Talk to CALCIE”
  - “Type a command”
  - “Start/Stop Vision Monitor”
  - “Recent Events”
  - “Open Debug Terminal”
  - “Permissions Checklist”
  - “Quit CALCIE”
- Do not build a full chat window yet.
- Optional lightweight popover:
  - last response
  - current route chosen
  - current monitor goal
  - last alert

### 9. Integrate Screen Vision as a Managed Background Capability

- The new `screen_vision` skill should become a **managed subsystem** from the shell app.
- Menu bar controls should allow:
  - start monitor with last-used goal
  - stop monitor
  - show current goal
  - show latest match summary
- Vision should remain:
  - alert-first
  - action-off by default
- Store recent monitor sessions/events locally and surface them in shell UI.

### 10. Permission and Safety Flow

- macOS shell must provide a user-visible permission status for:
  - microphone
  - accessibility
  - screen recording
  - notifications
  - optionally input monitoring
- Add a guided “Permissions Checklist” view/menu flow.
- Unsafe automation remains gated:
  - auto-actions from vision stay disabled by default
  - destructive agentic actions still require explicit confirmation

### 11. Logging and Observability

- Keep logs primarily in Python runtime.
- Add a simple event stream for the shell app:
  - route chosen
  - command received
  - skill started
  - skill completed
  - alert emitted
  - runtime error
- The shell app should show only user-relevant summaries, not raw logs.
- Route trace remains a developer feature and should stay available from terminal/debug mode.

### 12. File / Module Direction

- Keep existing core modules in Python.
- Add a dedicated local control layer in Python rather than bloating `calcie.py` further.
- Recommended new Python subsystem:
  - `calcie_local_api/` or equivalent service module for shell IPC
- Recommended new macOS app workspace:
  - separate top-level folder for Swift shell app
- Avoid mixing native Swift files into the current Python package tree without a clear boundary.

## Public Interfaces / Contracts

### Local Control API

Requests should be JSON and decision-complete for the shell app.

Examples:
- `POST /command`
  - input: `{ "text": "open chrome" }`
  - output: `{ "ok": true, "response": "...", "spoken": "...", "route": "app" }`
- `POST /vision/start`
  - input: `{ "goal": "watch for terminal build failures" }`
  - output: `{ "ok": true, "state": "vision_monitoring" }`
- `GET /status`
  - output includes:
    - current runtime state
    - active LLM
    - TTS provider
    - vision running flag
    - current monitor goal
    - permission warnings
- `GET /events`
  - returns recent user-safe event summaries for shell display

### Runtime Event Model

Each event should minimally include:
- `timestamp`
- `type`
- `summary`
- `severity`
- optional `route`
- optional `state`

## Test Plan

### Functional Scenarios

- Launch shell app when Python runtime is offline -> runtime starts and status becomes healthy
- Press hotkey -> CALCIE enters listening state -> submits voice -> returns response
- Use menu bar “Type a command” -> command reaches runtime -> routed skill response returns
- Start screen vision from menu bar -> runtime enters `vision_monitoring`
- Stop screen vision -> runtime exits monitor loop cleanly
- Trigger an alerting vision goal -> notification and spoken alert appear
- Open quick action like `open chrome` -> app skill executes through shell path
- Runtime crash -> shell shows degraded state and offers restart/reconnect behavior

### Safety / Failure Scenarios

- Missing Screen Recording permission -> status surfaces `needs_permission`
- Missing microphone permission -> hotkey flow degrades to typed input
- Vision provider unavailable -> monitor stays running only if graceful fallback is defined; otherwise shows clear error and stops
- Runtime unreachable -> shell does not hang; it shows offline state
- Auto-action disabled -> vision alert may notify but must not click/type

### Acceptance Criteria

- CALCIE can be used meaningfully without an open terminal window
- User can invoke CALCIE through menu bar + hotkey
- Existing core skills remain owned by Python runtime
- Screen vision can be started/stopped from the system surface
- Shell app shows trustworthy runtime state and permission issues
- Terminal remains optional for development, not required for daily use

## Assumptions and Defaults

- First target is **macOS only**
- First UX is **menu bar + global hotkey**
- Python remains the CALCIE brain and skill host
- Swift is used only for the native shell surface
- IPC uses **local HTTP JSON** first
- Wake-word stays secondary; **push-to-talk** is the primary desktop invoke path
- Vision remains **alert-first** and **safe by default**
- Full overlay/HUD is deferred until the background runtime + shell path is stable
- Full desktop chat app is deferred until menu bar flow proves the architecture
- Suggested markdown filename when implementation starts:
  - `CALCIE_MACOS_SYSTEM_APP_PLAN.md`
