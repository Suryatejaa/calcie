# CALCIE macOS System-App Transition Plan

## Summary

Move CALCIE from a terminal-first assistant into a **macOS-native background companion** while keeping the terminal as the **developer/debug surface**.

The first release should feel more like Jarvis through:
- a **menu bar app**
- a **global push-to-talk / invoke hotkey**
- **system notifications**
- a **background assistant runtime**
- integration with existing CALCIE skills for app control, vision, search, and desktop actions

This phase does **not** replace the current Python runtime. It wraps and stabilizes it behind a native macOS control layer.

## Key Decisions

- First target is **macOS only**
- First UX is **menu bar + global hotkey**
- Python remains the CALCIE brain and skill host
- Swift is used only for the native shell surface
- IPC uses **local HTTP JSON**
- Wake-word stays secondary; **push-to-talk** is the primary desktop invoke path
- Vision remains **alert-first** and **safe by default**

## Public Interfaces

### Local Control API

- `POST /command`
- `POST /voice/start`
- `POST /voice/stop`
- `POST /vision/start`
- `POST /vision/stop`
- `GET /status`
- `GET /events`
- `GET /health`

### Runtime Event Model

Each event should include:
- `timestamp`
- `type`
- `summary`
- `severity`
- optional `route`
- optional `state`

## Acceptance Criteria

- CALCIE can be used meaningfully without an open terminal window
- User can invoke CALCIE through menu bar + hotkey
- Existing core skills remain owned by Python runtime
- Screen vision can be started/stopped from the system surface
- Shell app shows trustworthy runtime state and permission issues
- Terminal remains optional for development, not required for daily use
