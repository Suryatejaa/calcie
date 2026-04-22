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
Screenshot -> Apple Vision OCR -> LLM JSON extraction -> dedup -> ChromaDB or JSONL
```

It is privacy-off by default. Enable it only when you want CALCIE to remember useful screen context:

```env
CALCIE_SCREEN_MEMORY_ENABLED=1
CALCIE_SCREEN_MEMORY_INTERVAL_S=45
CALCIE_SCREEN_MEMORY_DEDUP_THRESHOLD=0.15
CALCIE_SCREEN_MEMORY_STORE=auto
CALCIE_SCREEN_MEMORY_SKIP_IDLE_S=300
CALCIE_SCREEN_MEMORY_BACKGROUND_ENABLED=1
CALCIE_SCREEN_MEMORY_KEEP_CAPTURES=0
```

Storage:
- OCR snapshots: `.calcie/screen_memory/ocr/`
- JSONL fallback memories: `.calcie/screen_memory/memories.jsonl`
- Activity timeline: `.calcie/screen_memory/activity.jsonl`
- ChromaDB store, when `chromadb` is installed: `.calcie/screen_memory/chroma/`

Notes:
- macOS Apple Vision OCR is handled by `scripts/apple_vision_ocr.swift`.
- ChromaDB is optional; without it CALCIE uses conservative JSONL fuzzy dedup.
- The extractor filters obvious secrets/tokens/passwords and skips locked/idle screens where detectable.
- When `CALCIE_SCREEN_MEMORY_ENABLED=1`, CALCIE starts a background memory loop even if no vision monitor goal is running.
- `vision stop` stops alert monitoring only; it does not stop the memory loop while screen memory remains enabled.

### 5) TTS Design

Provider sequence:
1. Google TTS (`CALCIE_TTS_PROVIDER=auto|google`)
2. Edge TTS
3. Offline `pyttsx3`

Google TTS auth sources:
- explicit `GOOGLE_OAUTH_ACCESS_TOKEN`
- ADC token via `gcloud auth application-default print-access-token`

Quota project resolution order:
1. `CALCIE_GOOGLE_TTS_QUOTA_PROJECT`
2. `GOOGLE_CLOUD_QUOTA_PROJECT`
3. `GOOGLE_CLOUD_PROJECT`
4. ADC file `~/.config/gcloud/application_default_credentials.json`

### 6) Search LLD

Provider cascade:
1. Tavily
2. Exa
3. DDGS

Flow:
1. Provider returns top URLs/snippets.
2. Scrape top-K pages (`CALCIE_SEARCH_SCRAPE_TOP_K`).
3. Build source blob.
4. Run LLM synthesis prompt (`SEARCH_SYNTH_SYSTEM_PROMPT` + template).
5. Return concise answer and optional source list.

### 7) Coding Safety LLD

`code_tools.py` enforces:
- repository-scoped file operations
- proposal artifacts under `.calcie/`
- explicit apply/discard lifecycle
- syntax validation for Python proposals before apply

Lifecycle:
1. `code propose ...` creates proposal + backup metadata.
2. `code diff <id>` previews patch.
3. `code apply <id>` writes change intentionally.
4. `code discard <id>` drops proposal.

### 8) Data Model (Persisted)

Local:
- `calcie_history.db`: chat timeline (`role`, `content`, timestamp/id)
- `calcie_facts.json`: long-term fact strings
- `calcie_profile.json`: structured profile context
- `.calcie/`: proposals, backups, tool artifacts

Remote (sync backend):
- device registry
- command queue (poll + ack)
- shared messages
- shared facts

### 9) Failure and Fallback Strategy

- Skill route miss -> LLM fallback.
- LLM provider failure -> next provider in chain (`auto` mode).
- Google TTS auth/quota failures -> Edge TTS -> pyttsx3.
- Tavily/Exa quota failures -> DDGS fallback.
- Cross-device unavailable -> local handling continues.

---

## Skills

### 1) App Access
Examples:
- `open chrome`
- `open amazon in chrome`
- `open voice memos`
- `play music`
- `play <song>`
- `play video song <name>`

### 2) Searching
Examples:
- `search latest ai news`
- `who won last night ipl`
- `latest ipl points table`
- `check live ipl score`
- `search devops role jobs`
- `what are today's nba scores`
- `what is the weather`
- `weather in hyderabad`

Behavior:
- tries providers in cascade
- scrapes top pages
- synthesizes direct answer + confidence line
- optional source list
- routes job searches into Job Hunter when enabled
- routes supported sports queries into ESPN MCP when enabled
- routes weather queries into a dedicated weather path before generic search

### 3) Coding (Safe Mode)
Examples:
- `code tree`
- `code read calcie.py lines 1-120`
- `code search wake word`
- `code propose calcie.py :: add helper`
- `code proposals`
- `code diff <id>`
- `code apply <id>`

Safety:
- proposal/apply workflow
- no blind write-over of working code
- proposal metadata and backups stored under `.calcie/`

### 4) Computer Control
Examples:
- `control status`
- `control arm`
- `click at 500 400`
- `scroll down 600`
- `press enter`
- `take screenshot test`

Safety:
- arm-lock window
- optional dry-run mode
- fail-safe backend checks

### 5) Agentic Computer Use
Examples:
- `order a 72x60 mattress from amazon`
- `play one piece on netflix in chrome`

Behavior:
- builds JSON plan with allowed tools
- executes step-by-step with guardrails
- stops before payment/place-order
- optional confirm/cancel approval gate

---

## LLM Providers

Set:
- `CALCIE_LLM_PROVIDER=auto|gemini|openai|claude|grok|ollama`

Notes:
- `auto` selects best available provider and falls back.
- explicit provider runs strict mode.
- `ollama` is local/offline fallback path.

---

## Voice + TTS

Provider chain:
- `google_tts` (if enabled/configured) -> `edge_tts` -> `pyttsx3`

Main toggles:
- `CALCIE_TTS_PROVIDER=auto|google|edge|offline`
- `CALCIE_TTS_DEBUG=1` (provider/debug logs)
- `CALCIE_TTS_CHUNK_CHARS=170`

Feedback/bridge controls:
- `CALCIE_FEEDBACK_ACK_SPEAK_ENABLED=0|1`
- `CALCIE_FEEDBACK_BRIDGE_KINDS=...`
- To disable bridge speaking only:
  - `CALCIE_FEEDBACK_BRIDGE_KINDS=none`

### Google TTS (ADC/OAuth)

Required for Cloud TTS API calls:
1. Install **Google Cloud CLI** (not `pip install gcloud` package).
2. Run:
   - `gcloud auth application-default login`
   - `gcloud auth application-default set-quota-project <PROJECT_ID>`
3. Optional env override:
   - `CALCIE_GOOGLE_TTS_QUOTA_PROJECT=<PROJECT_ID>`

Common Google TTS env:
- `CALCIE_GOOGLE_TTS_ENDPOINT`
- `CALCIE_GOOGLE_TTS_MODEL`
- `CALCIE_GOOGLE_TTS_VOICE_NAME`
- `CALCIE_GOOGLE_TTS_LANGUAGE_CODE`
- `CALCIE_GOOGLE_TTS_AUDIO_ENCODING`
- `CALCIE_GOOGLE_TTS_SPEAKING_RATE`
- `CALCIE_GOOGLE_TTS_PITCH`
- `CALCIE_GOOGLE_TTS_PROMPT`

Important:
- `input.prompt` is supported only for Gemini TTS models.
- Chirp3 voices should be used without prompt semantics.

---

## Quick Start (Desktop)

```bash
python3 -m pip install -r requirements.txt
python3 calcie.py
```

Minimum `.env` you usually need:

```env
# LLM
CALCIE_LLM_PROVIDER=auto
GEMINI_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GROK_API_KEY=

# Search
TAVILY_API_KEY=
EXA_API_KEY=
CALCIE_SEARCH_PROVIDER=auto

# TTS
CALCIE_TTS_PROVIDER=auto
CALCIE_TTS_DEBUG=0
```

---

## Search Provider Strategy

Current fallback order:
1. Tavily
2. Exa
3. DDGS + page extraction

Useful knobs:
- `CALCIE_SEARCH_PROVIDER=auto|tavily|exa|ddgs`
- `CALCIE_TAVILY_MODE=search|research`
- `CALCIE_RESEARCH_TIMEOUT_S=24`
- `CALCIE_RESEARCH_POLL_S=1.0`
- `CALCIE_SEARCH_SCRAPE_TOP_K=3`
- `CALCIE_SEARCH_SYNTH_TOKENS=220`
- `CALCIE_SEARCH_SHOW_SOURCES=1`
- `CALCIE_SEARCH_DEBUG=0`
- `CALCIE_SEARCH_LLM_PROVIDER=auto`

Weather-specific knobs:
- `WEATHER_API_KEY=<weatherapi key>`
- `CALCIE_WEATHER_DEFAULT_QUERY=Hyderabad`
- generic prompts like `what is the weather` use the default city fallback when needed

---

## Sync Backend (Laptop + Mobile)

Run local backend:

```bash
python3 -m pip install -r calcie_cloud/requirements.txt
python3 -m uvicorn calcie_cloud.server:app --host 0.0.0.0 --port 8000
```

Desktop sync env:
- `CALCIE_SYNC_ENABLED=1`
- `CALCIE_SYNC_BASE_URL=<backend url>`
- `CALCIE_SYNC_USER_ID=<same on all devices>`
- `CALCIE_DEVICE_TYPE=laptop`
- `CALCIE_DEVICE_ID=laptop`

### Deploy backend (Render/Railway/Fly)

Render non-Docker:
- Build command: `pip install -r calcie_cloud/requirements.txt`
- Start command: `python -m uvicorn calcie_cloud.server:app --host 0.0.0.0 --port $PORT`

Docker path:
- `calcie_cloud/Dockerfile`
- health check: `/health`

---

## Mobile Clients

### mobile_v1
- Lightweight command relay + app open/play support.
- Polling-based: app must be running for real-time execution.

### mobile_v2 (v2.1)
- Action cards for high-risk commands.
- Settings persistence.
- Outbox retry.
- In-app TTS.
- Foreground-resume sync.

Run:

```bash
cd mobile_v2
npm install
npx expo start --lan
```

Note:
- Expo Go limitations still apply.
- Closed-app real-time automation needs production build + push/background handling.

---

## Job Hunter Handoff

CALCIE can detect job-search requests like:
- `search devops role jobs`
- `find backend jobs in hyderabad`
- `search remote sre jobs`

When enabled, CALCIE starts the local Job Hunter app and opens a browser page like:

```text
http://127.0.0.1:3000/?q=devops&location=hyderabad&autorun=1
```

This lets the browser UI handle:
- merged job fetch (RapidAPI + Apify/Naukri path)
- ranking
- cover letter generation
- application tracking

### Job Hunter setup

```bash
cd job-hunter
npm install
```

The server reads the repo root `.env`.

Main files:
- `job-hunter/server.js`
- `job-hunter/index.html`

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
