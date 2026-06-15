# CALCIE

CALCIE is a local-first personal AI companion + agent built in Python.

It runs on laptop (main runtime), supports cross-device sync with Android clients, and can combine multiple skills:
- chat (multi-LLM with fallback)
- search + synthesis
- sports-aware search routing
- job-search handoff UI
- app access and media actions
- guarded coding workflow
- desktop computer control
- essential agentic task execution
- macOS menu bar shell

---

## What Is New (Latest)

- Added **router + orchestration layer** with typo-tolerant command arbitration (`serch`, `controll`, `cod` style inputs).
- Split giant prompt into **small route-specific prompts** (`general`, `web-grounded`, `profile`, `code`, `agentic`).
- Reduced context load with **request-aware history trimming** and selective profile injection.
- Search now uses **provider cascade + synthesis**:
  - Tavily -> Exa -> DDGS fallback
  - scrape top sources
  - synthesize with LLM
- Added **job-search detection + Job Hunter handoff**:
  - CALCIE can route job queries to the local `job-hunter` web app
  - browser UI becomes the workspace instead of dumping job results into CLI
- Added **sports-specific routing**:
  - ESPN MCP path for supported leagues like NBA/NFL/UFC/F1
  - cricket/IPL live score uses the CREX series page parser before falling back
- Added **deployment planning**:
  - backend + DB shape
  - DMG/signing/notarization pipeline
  - website/docs launch flow
  - update notification manifest
  - first-run ChatGPT memory import onboarding
- Added **first-run profile import plumbing**:
  - Advanced Options can copy the ChatGPT memory export prompt
  - pasted fenced response imports into local-only `calcie_profile.local.json`
  - raw import backup is stored under `.calcie/profile_imports/`
- Added **weather-specific handling**:
  - direct WeatherAPI path when `WEATHER_API_KEY` is valid
  - grounded Gemini fallback when the dedicated weather provider is unavailable
  - default-city fallback for generic prompts like `what is the weather`
- TTS upgraded with provider chain:
  - Google TTS (OAuth/ADC) -> Edge TTS -> pyttsx3 fallback
- Google TTS now supports ADC quota-project detection from local credentials file.
- macOS shell now supports:
  - packaged `CALCIE.app`
  - menu bar control surface
  - **hold Right Option** to talk
  - launch-at-login toggle for the packaged app
  - native permission-state checks for microphone/accessibility/screen recording/notifications
  - runtime identity + restart controls for local backend recovery
  - compact popover + floating `Advanced Options` panel
  - bundle build/signing diagnostics in the app
  - **CALCIE Player Phase 1**:
    - one app-owned `MediaSessionManager`
    - one reusable player window reference
    - one reusable `WKWebView` surface
    - resolved YouTube / YouTube Music watch-page loading inside the owned player
    - desktop media controls for `play`, `pause`, `resume`, `next`, `previous`, and `play again`
    - in-player controls for mute, volume, speed, and seek
    - lightweight history plus persisted last-session restore across app restarts
- Local API access logs are disabled by default to keep CALCIE output clean.
- Added a stable-signing workflow helper for packaged macOS installs:
  - `./scripts/check_calcie_codesign.sh`
  - `CALCIE_CODESIGN_SETUP.md`
- Added/updated mobile clients:
  - `mobile_v1` (basic)
  - `mobile_v2` (v2.1 safety/action cards/settings/offline outbox retry)

---

## Repository Layout

```text
calcie.py                         # Main runtime (desktop assistant)
calcie_core/
  intent.py                       # Activation + intent classification
  orchestration.py                # CommandArbiter (router/orchestrator)
  prompts.py                      # Small route-specific prompts
  search_utils.py                 # Parsing/normalization helpers
  code_tools.py                   # Safe code read/proposal/apply primitives
  sync_client.py                  # Cloud sync client
  feedback_phrases.json           # ACK/bridge phrase banks
  skills/
    app_access.py
    searching.py
    coding.py
    computer_control.py
    agentic_computer_use.py
    docs/
calcie_cloud/                     # FastAPI sync backend
mobile_v1/                        # Android client v1
mobile_v2/                        # Android client v2.1
job-hunter/                       # Local jobs UI + API handoff app
calcie_local_api/                 # Local HTTP runtime control API
calcie_macos/                     # Native macOS menu bar shell
```

---

## Core Runtime Flow

1. `python3 calcie.py`
2. Load env + profile + facts + recent chat history.
3. User input (voice/text) enters router.
4. `CommandArbiter` scores route and optionally rewrites leading typo command.
5. Skill dispatch order:
   - coding
   - vision
   - agentic computer-use
   - app access
   - computer control
   - searching
6. If no skill handles, CALCIE calls LLM with compact route-specific prompt.
7. Response is printed and spoken via TTS queue.
8. If sync enabled, commands/messages/facts are synced with backend.

---

## LLD (Low-Level Design)

### 1) Main Components

| Component | File | Responsibility |
|---|---|---|
| Runtime Orchestrator | `calcie.py` | Input loop, route dispatch, LLM fallback, TTS pipeline, persistence, sync hooks |
| Command Router | `calcie_core/orchestration.py` | Fuzzy command arbitration, typo correction, route confidence scoring |
| Prompt Layer | `calcie_core/prompts.py` | Route-specific compact prompts and synthesis templates |
| Intent Utilities | `calcie_core/intent.py` | Activation detection, greeting/query classification, intent helpers |
| Search Utilities | `calcie_core/search_utils.py` | Query normalization, sports/news parsing, formatting helpers |
| Skills Layer | `calcie_core/skills/*.py` | Deterministic handlers for app/search/code/computer/agentic tasks |
| Code Safety Layer | `calcie_core/code_tools.py` | Read-only scans + proposal/diff/apply guarded workflow |
| Sync Client | `calcie_core/sync_client.py` | Device registration, polling, command/message/facts sync |
| Cloud Sync API | `calcie_cloud/server.py` | Backend queue/state for cross-device coordination |

### 2) Route Arbitration Contract

`CommandArbiter.decide(user_input, strict_flags) -> RouteDecision`

`RouteDecision` fields:
- `route`: `coding|agentic|app|computer|search|None`
- `confidence`: float score after keyword/leading-verb weighting
- `reason`: score rationale for debug
- `rewritten_input`: typo-fixed command (example: `serch` -> `search`)

Dispatch policy in `calcie.py`:
1. Build strict flags from deterministic intent checks.
2. Ask arbiter for best route.
3. Try routed skill first (with rewritten input when needed).
4. Fallback through default skill order.
5. If no skill handles, call LLM.

### 3) Skill Interface Contract

Each skill exposes:
- intent check (`is_*` or deterministic extractor)
- command handler returning `(response_text, speech_text)` or `(None, None)`

Implemented skills:
- `AppAccessSkill`
- `SearchingSkill`
- `CodingSkill`
- `ComputerControlSkill`
- `AgenticComputerUseSkill`
- `ScreenVisionSkill`
- `ScreenMemoryPipeline` behind `ScreenVisionSkill`

### 4) Request Processing Pipeline

1. Input accepted from voice/text.
2. Store user message to SQLite.
3. Emit optional ACK feedback phrase.
4. Try skill dispatch via router.
5. If skill handled:
   - print result
   - optional bridge phrase + speak
   - save assistant response
6. Else build minimal LLM context:
   - trimmed history
   - route-specific system prompt
   - profile context only when relevant
7. Stream LLM output.
8. Speak output via TTS chain.
9. Persist response locally and optionally to sync backend.

### Screen Memory

CALCIE has an optional screen-memory pipeline:

```text
User
  ↓
Native Desktop Shell
  ↓
Local Runtime
  ↓
Memory Layer
  ↓
Tool & Automation Layer
  ↓
AI Provider Routing
  ↓
Response Generation
```

Current implementation:

```text
macOS Shell
      ↓
Local Runtime
      ↓
Local Control API
      ↓
Memory + Skills
      ↓
AI Providers
```

---

## Design Philosophy

### Local-First

Your assistant should continue functioning even when cloud services are unavailable.

### Memory-Driven

Conversations should build upon previous interactions rather than starting from zero.

### Provider Agnostic

CALCIE is not tied to a single AI vendor.

It can route requests across multiple providers and evolve as the AI ecosystem changes.

### Human-Centric

The assistant should adapt to the user rather than forcing the user to adapt to the assistant.

---

## Sports Requests

Supported sports requests can use an ESPN MCP-backed path, for example:
- `what are today's nba scores`
- `latest nfl standings`
- `ufc rankings`

Current intent:
- supported ESPN leagues -> sports MCP path
- unsupported leagues like **IPL/cricket** -> fallback web/sports search

Useful env:

```env
CALCIE_SPORTS_MCP_ENABLED=1
CALCIE_SPORTS_MCP_URL=https://mrbridge--espn-mcp-server.apify.actor/mcp
CALCIE_SPORTS_MCP_TIMEOUT_S=10
```

Note:
- the ESPN MCP path is intended for ESPN-supported sports only
- IPL/cricket requests should continue using fallback search

---

## macOS Permissions (Computer Control)

If you run CALCIE from terminal/Xcode, grant permissions to those host apps.

If you run packaged `CALCIE.app`, grant permissions to **CALCIE.app** itself.

Relevant macOS permissions:
1. Privacy & Security -> Accessibility
2. Privacy & Security -> Screen Recording
3. Privacy & Security -> Microphone
4. (Optional) Input Monitoring

Then restart the app you granted.

---

## macOS Shell

CALCIE includes a native menu bar shell under `calcie_macos/`.

Current behavior:
- menu bar app
- typed command entry
- voice start/stop from UI
- runtime status + recent events
- runtime identity + restart action
- packaged app bundle support
- compact menu with advanced settings split into a floating panel
- **hold Right Option** for talk-to-CALCIE
- launch-at-login toggle for `CALCIE.app`
- app-owned CALCIE Player surface with one reusable window and one reusable web view
- desktop media commands now prefer CALCIE Player when the shell is active:
  - `play`
  - `pause`
  - `resume`
  - `next`
  - `previous`
  - `play again`
  - `mute` / `unmute`
  - `volume up` / `volume down` / `set volume to 40`
  - `faster` / `slower` / `speed 1.5x`
  - `forward 10 seconds` / `rewind 15 seconds`

Build/install:

```bash
./scripts/build_calcie_macos_app.sh
./scripts/install_calcie_macos_app.sh
```

For more stable macOS privacy permissions across reinstalls, sign the app with a real certificate before building:

```bash
export CALCIE_CODESIGN_IDENTITY="Apple Development: Your Name (TEAMID)"
./scripts/install_calcie_macos_app.sh
```

Installed app path:

```text
~/Applications/CALCIE.app
```

### CALCIE Player (Phase 1)

The first player milestone is intentionally simple and architecture-first:

- one app-level `MediaSessionManager`
- one CALCIE-owned player window
- one reusable `WKWebView`
- no normal browser tabs for desktop playback experiments
- query-aware resolver that prefers stronger watch-page matches over blind first-result loading
- lightweight session metadata:
  - current platform
  - last resolved query
  - last playable title/url
  - recent remembered history
- persisted player session under `~/.calcie/runtime/media_session_state.json`

Current status:
- you can open the player from the mini menu or Advanced Options
- it uses watch-page loading for YouTube / YouTube Music inside the CALCIE-owned surface
- desktop media commands can reuse this same surface for:
  - `play <song>`
  - `play video song <name>`
  - `pause`
  - `resume`
  - `next`
  - `previous`
  - `play again`
  - `mute`
  - `unmute`
  - `volume up`
  - `volume down`
  - `set volume to 40`
  - `faster`
  - `slower`
  - `speed 1.5x`
  - `forward 10 seconds`
  - `rewind 15 seconds`
- after restart, `resume` / `play music` can restore the last known playable session instead of starting empty
- future queue work should keep extending this same surface instead of opening new tabs

---

## Safety Boundaries

- Coding skill uses proposal/apply workflow.
- Agentic planner enforces allowed tools and limited step count.
- Shopping tasks stop at cart/review stage.
- Computer control can require arm lock and dry-run.
- Cross-device commands are explicit (`on mobile`, `on laptop`) and can require approvals in mobile v2.

---

## Troubleshooting

### `uvicorn: command not found`
Use module form:
```bash
python3 -m uvicorn calcie_cloud.server:app --host 0.0.0.0 --port 8000
```

### Google TTS 403 quota-project error
Run:
```bash
gcloud auth application-default set-quota-project <PROJECT_ID>
```
or set:
```env
CALCIE_GOOGLE_TTS_QUOTA_PROJECT=<PROJECT_ID>
```

### Google TTS 400 “Prompt is only supported for Gemini TTS”
Use Chirp3 without Gemini prompt semantics; keep `CALCIE_GOOGLE_TTS_PROMPT` empty for Chirp voice setups.

### Apps opening in browser instead of app
Tune app mode:
- desktop: `CALCIE_YOUTUBE_OPEN_MODE`, `CALCIE_YTMUSIC_OPEN_MODE`, `CALCIE_MEDIA_OPEN_MODE`
- mobile: `EXPO_PUBLIC_CALCIE_APP_OPEN_MODE=app_only`

### Menu bar app still responds to old hotkey
Rebuild/reinstall the packaged app:

```bash
./scripts/install_calcie_macos_app.sh
```

Then quit any stale CALCIE instance before reopening `~/Applications/CALCIE.app`.

### Local API request logs are cluttering output
By default they are now disabled.

To re-enable:

```env
CALCIE_LOCAL_API_ACCESS_LOG=1
CALCIE_LOCAL_API_LOG_LEVEL=info
```

### Command typo bypasses skill and falls to generic LLM
Enable/debug router:
- `CALCIE_ROUTER_DEBUG=1`
- tune thresholds:
  - `CALCIE_ROUTER_CONFIDENCE_THRESHOLD`
  - `CALCIE_ROUTER_AMBIGUOUS_DELTA`
  - `CALCIE_ROUTER_LEADING_FIX_THRESHOLD`

---

## Security

- Never commit real keys in `.env`.
- Rotate leaked keys immediately.
- Keep personal profile/facts files private if they contain sensitive data.
- Run release hygiene before packaging:

```bash
./scripts/check_release_hygiene.py
```

This fails if a release may include `.env`, `.calcie`, screen captures, OCR dumps, local profile imports, local DBs, or obvious secret tokens.

Dev/prod release flow:

```bash
./scripts/configure_release_remotes.sh
./scripts/promote_calcie_prod.sh
```

See `CALCIE_RELEASE_FLOW.md` for the full dev -> QA -> prod process, Render backend production notes, and Vercel website deployment flow.

Build a local macOS DMG:

```bash
CALCIE_CODESIGN_IDENTITY="Apple Development: your@example.com (TEAMID)" \
CALCIE_RELEASE_CHANNEL=alpha \
./scripts/build_calcie_dmg.sh release
```

The DMG is written to `dist/` and release metadata is written to `dist/calcie_release_manifest.json`.
Set `CALCIE_RELEASE_PUBLIC_BASE_URL` and `CALCIE_RELEASE_NOTES_URL` before final release so the metadata can be published to the update manifest endpoint.

Publish release metadata after uploading the DMG:

```bash
export CALCIE_CLOUD_BASE_URL="https://your-calcie-backend.example.com"
export CALCIE_CLOUD_ADMIN_TOKEN="<your-admin-token>"
./scripts/publish_calcie_release.py \
  --download-url https://your-download-host/CALCIE-0.1.0-1-alpha.dmg \
  --release-notes-url https://your-site/releases/0.1.0
```

Preview without publishing:

```bash
./scripts/publish_calcie_release.py --dry-run --allow-empty-url
```

Website/docs skeleton:

```text
index.html
docs/setup.html
docs/privacy.html
releases/0.1.0.html
styles.css
main.js
```

Use this static site for the first public launch page, setup guide, privacy page, and release notes. Replace the placeholder download button after uploading the DMG.

---

## Quick Command Cookbook

- `search latest ai news`
- `check live ipl score`
- `who won last night ipl`
- `what are today's nba scores`
- `search devops role jobs`
- `open amazon in chrome`
- `play music`
- `play video song perfect`
- `code tree`
- `code read calcie.py lines 1-120`
- `control status`
- `control arm`
- `order a 72x60 mattress from amazon`
- `play one piece on netflix in chrome`
