# CALCIE

CALCIE is a local-first personal AI companion + agent built in Python.

It runs on laptop (main runtime), supports cross-device sync with Android clients, and can combine multiple skills:
- chat (multi-LLM with fallback)
- search + synthesis
- app access and media actions
- guarded coding workflow
- desktop computer control
- essential agentic task execution

---

## What Is New (Latest)

- Added **router + orchestration layer** with typo-tolerant command arbitration (`serch`, `controll`, `cod` style inputs).
- Split giant prompt into **small route-specific prompts** (`general`, `web-grounded`, `profile`, `code`, `agentic`).
- Reduced context load with **request-aware history trimming** and selective profile injection.
- Search now uses **provider cascade + synthesis**:
  - Tavily -> Exa -> DDGS fallback
  - scrape top sources
  - synthesize with LLM
- TTS upgraded with provider chain:
  - Google TTS (OAuth/ADC) -> Edge TTS -> pyttsx3 fallback
- Google TTS now supports ADC quota-project detection from local credentials file.
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
```

---

## Core Runtime Flow

1. `python3 calcie.py`
2. Load env + profile + facts + recent chat history.
3. User input (voice/text) enters router.
4. `CommandArbiter` scores route and optionally rewrites leading typo command.
5. Skill dispatch order:
   - coding
   - agentic computer-use
   - app access
   - computer control
   - searching
6. If no skill handles, CALCIE calls LLM with compact route-specific prompt.
7. Response is printed and spoken via TTS queue.
8. If sync enabled, commands/messages/facts are synced with backend.

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

Behavior:
- tries providers in cascade
- scrapes top pages
- synthesizes direct answer + confidence line
- optional source list

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

## macOS Permissions (Computer Control)

Allow the terminal host app in:
1. Privacy & Security -> Accessibility
2. Privacy & Security -> Screen Recording
3. (Optional) Input Monitoring

Then restart terminal app.

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

---

## Quick Command Cookbook

- `search latest ai news`
- `who won last night ipl`
- `open amazon in chrome`
- `play music`
- `play video song perfect`
- `code tree`
- `code read calcie.py lines 1-120`
- `control status`
- `control arm`
- `order a 72x60 mattress from amazon`
- `play one piece on netflix in chrome`

