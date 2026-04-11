# CALCIE

CALCIE is a local-first personal AI companion/agent built in Python.
It supports:
- multi-LLM chat (Gemini, Claude, OpenAI, Grok, Ollama)
- voice input + voice output
- smart wake/intent activation
- web research with provider fallback
- guarded coding assistance on your repository
- desktop app/media control
- basic computer control (screenshot/click/scroll/type/keys)

This file is the single project-level guide for setup, architecture, commands, safety, and troubleshooting.

## 1) Current architecture

Main runtime:
- `calcie.py` -> app entry, chat loop, LLM orchestration, voice loop, skill routing

Core modules:
- `calcie_core/intent.py` -> activation/classification/intent logic
- `calcie_core/search_utils.py` -> search/sports/news utility parsing
- `calcie_core/code_tools.py` -> safe code read + proposal/apply workflow
- `calcie_core/sync_client.py` -> cloud sync client for messages/facts/device commands

Skills:
- `calcie_core/skills/app_access.py`
- `calcie_core/skills/agentic_computer_use.py`
- `calcie_core/skills/coding.py`
- `calcie_core/skills/searching.py`
- `calcie_core/skills/computer_control.py`

Skill docs:
- `calcie_core/skills/docs/app_access.md`
- `calcie_core/skills/docs/agentic_computer_use.md`
- `calcie_core/skills/docs/coding.md`
- `calcie_core/skills/docs/searching.md`
- `calcie_core/skills/docs/computer_control.md`

Persistence:
- `calcie_history.db` -> SQLite chat history
- `calcie_facts.json` -> long-term facts memory
- `.calcie/` -> proposals, backups, computer artifacts

Cloud/mobile V1:
- `calcie_cloud/server.py` -> FastAPI sync backend
- `mobile_v1/` -> Android-first Expo app scaffold

## 2) Runtime flow

1. Start `python3 calcie.py`.
2. CALCIE loads `.env`, system prompt, profile facts, and recent chat history.
3. Input loop supports:
   - voice wake + speech input
   - text mode fallback
4. Message routing order in chat:
   - coding skill
   - agentic computer-use skill (essential tasks only)
   - app access skill
   - computer control skill
   - searching skill
   - then general LLM response
5. Assistant response is streamed and spoken with TTS queue.
6. If sync is enabled, CALCIE polls inbound cross-device commands and executes locally.

## 3) LLM provider behavior

Provider selector:
- `CALCIE_LLM_PROVIDER=auto|gemini|openai|claude|grok|ollama`
- Alias supported: `CALCIE_LLM_MODE`

Behavior:
- `auto` -> tries best available provider, then fallback chain
- explicit provider -> strict mode (no automatic switching)
- agentic planner can use a separate provider via `CALCIE_COMPUTER_USE_PROVIDER`

Gemini model preference:
- `GEMINI_MODEL` sets first-choice model in Gemini list
- project currently favors `gemini-robotics-er-1.5-preview` when configured

## 4) Skill capabilities

### App access
Examples:
- `open chrome`
- `open amazon in chrome`
- `open github.com in safari`
- `play music` (YouTube Music default)
- `play <song name>` (YouTube Music search)
- `play video song <name>` (YouTube search)

Notes:
- macOS app resolution handles spaced/non-spaced app names (for example Voice Memos/VoiceMemos)
- media mode can be app-first with browser fallback

### Agentic computer use (multi-step)
Examples:
- `order a usb c hub on amazon`
- `play the movie interstellar on netflix in chrome`
- `do this on my screen and use search if needed`

Behavior:
- uses an LLM-generated JSON plan and executes cross-tool steps
- can combine app + search + computer commands in one request
- defaults to essential tasks only
- never auto-finalizes payment/place-order
- sanitizes LLM plans before execution (rewrites/drops invalid tool steps)
- stops early after repeated failed steps to avoid runaway bad actions
- with confirmation enabled, CALCIE previews plan first and waits for `confirm`
- supports cross-device routing phrases: `... on mobile` / `... on laptop`

### Coding (safe proposal workflow)
Examples:
- `code tree`
- `code list`
- `code read calcie.py lines 1-120`
- `code search wake word`
- `code explain how app routing works`
- `code propose calcie.py :: add a new helper`
- `code proposals`
- `code diff <proposal_id>`
- `code apply <proposal_id>`
- `code discard <proposal_id>`

Safety model:
- no direct arbitrary writes
- changes go through proposal + diff + explicit apply
- `.py` proposals are syntax-validated before storage

### Searching (multi-provider + synthesis)
Examples:
- `search latest ai news`
- `who won last night ipl`
- `latest ipl points table`

Provider cascade:
1. Tavily
2. Exa
3. DDGS

Result model:
- scrapes content from top results
- synthesizes a concise fact summary
- includes provider attempts and sources

### Computer control
Examples:
- `control status`
- `control arm`
- `take screenshot test`
- `scroll down 600`
- `click at 500 400`
- `type hello world`
- `press enter`
- `hotkey cmd+k`
- `control disarm`

Safety model:
- arm-lock window (time-bound)
- dry-run mode
- fail-safe enabled in `pyautogui`

## 5) Environment variables (full catalog)

### API keys
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`
- `OPENAI_API_KEY`
- `GROK_API_KEY`
- `TAVILY_API_KEY`
- `EXA_API_KEY`

### LLM routing
- `CALCIE_LLM_PROVIDER` (`auto|gemini|openai|claude|grok|ollama`)
- `CALCIE_LLM_MODE` (alias for provider)
- `GEMINI_MODEL`

### Response/context tuning
- `CALCIE_MAX_CONTEXT_MESSAGES`
- `CALCIE_MAX_CONTEXT_MESSAGES_WEB`
- `CALCIE_MAX_OUTPUT_TOKENS`
- `CALCIE_QUICK_MAX_OUTPUT_TOKENS`
- `CALCIE_CODE_MAX_OUTPUT_TOKENS`
- `CALCIE_CODE_MAX_FILE_CHARS`

### Search behavior
- `CALCIE_SEARCH_PROVIDER` (`auto|tavily|exa|ddgs`)
- `CALCIE_SEARCH_ALLOW_FALLBACK` (`0|1`)
- `CALCIE_RESEARCH_TIMEOUT_S`
- `CALCIE_RESEARCH_POLL_S`
- `CALCIE_DDGS_FALLBACK_RESULTS`
- `CALCIE_USE_EXTERNAL_WEB_TOOLS` (`0|1`, legacy path)

### Coding skill
- `CALCIE_CODE_TOOLS_ENABLED` (`0|1`)

### App/media skill
- `CALCIE_MEDIA_OPEN_MODE` (`app_first|browser_only`)
- `CALCIE_YOUTUBE_OPEN_MODE` (`app_only|app_first|browser_only`)
- `CALCIE_YTMUSIC_OPEN_MODE` (`app_only|app_first|browser_only`)
- `CALCIE_YTMUSIC_APP_NAME` (optional override)
- `CALCIE_YOUTUBE_APP_NAME` (optional override)

### Agentic computer-use skill
- `CALCIE_AGENTIC_COMPUTER_USE_ENABLED` (`0|1`)
- `CALCIE_AGENTIC_COMPUTER_USE_ESSENTIAL_ONLY` (`0|1`)
- `CALCIE_COMPUTER_USE_PROVIDER` (`auto|openai|gemini|claude`)
- `CALCIE_COMPUTER_USE_MAX_STEPS` (`2..12`)
- `CALCIE_COMPUTER_USE_AUTO_ARM` (`0|1`)
- `CALCIE_COMPUTER_USE_REQUIRE_CONFIRM` (`0|1`)

### Cross-device sync (mobile/laptop V1)
- `CALCIE_SYNC_ENABLED` (`0|1`)
- `CALCIE_SYNC_BASE_URL` (example: `http://127.0.0.1:8000`)
- `CALCIE_SYNC_USER_ID`
- `CALCIE_DEVICE_TYPE` (`laptop|mobile`)
- `CALCIE_DEVICE_ID`
- `CALCIE_MOBILE_DEVICE_ID`
- `CALCIE_LAPTOP_DEVICE_ID`
- `CALCIE_SYNC_POLL_SECONDS`

### Computer control skill
- `CALCIE_COMPUTER_CONTROL_ENABLED` (`0|1`)
- `CALCIE_COMPUTER_REQUIRE_ARM` (`0|1`)
- `CALCIE_COMPUTER_ARM_SECONDS` (`10..300`)
- `CALCIE_COMPUTER_DRY_RUN` (`0|1`)

### TTS voice styling
- `CALCIE_TTS_VOICE` (default: `en-US-AvaNeural`)
- `CALCIE_TTS_RATE`
- `CALCIE_TTS_PITCH`

## 6) Install and run

```bash
python3 -m pip install -r requirements.txt
python3 calcie.py
```

Optional V1 sync backend:
```bash
python3 -m pip install -r calcie_cloud/requirements.txt
python3 -m uvicorn calcie_cloud.server:app --host 0.0.0.0 --port 8000
```

Recommended first boot:
1. set at least one LLM API key in `.env`
2. keep `CALCIE_COMPUTER_DRY_RUN=1` initially
3. test:
   - `control status`
   - `search latest ai news`
   - `code tree`
   - `open chrome`

### Mobile V1 quick start
1. Start sync backend:
```bash
uvicorn calcie_cloud.server:app --host 0.0.0.0 --port 8000
```
2. On laptop `.env`:
- `CALCIE_SYNC_ENABLED=1`
- `CALCIE_SYNC_BASE_URL=<reachable URL>`
- `CALCIE_SYNC_USER_ID=<same on all devices>`
- `CALCIE_DEVICE_ID=laptop`
3. In `mobile_v1/.env`, set:
- `EXPO_PUBLIC_CALCIE_API_BASE_URL=<reachable URL>`
- `EXPO_PUBLIC_CALCIE_USER_ID=<same as laptop>`
- `EXPO_PUBLIC_CALCIE_DEVICE_ID=mobile`
- `EXPO_PUBLIC_CALCIE_LAPTOP_DEVICE_ID=laptop`
4. Run mobile app:
```bash
cd mobile_v1
npm install
npx expo start --lan
```

## 6.1) Backend deployment (production)

Fast path:
1. Use Docker with `calcie_cloud/Dockerfile`.
2. Deploy to Render/Railway/Fly (any Docker host).
3. Set env:
- `CALCIE_SYNC_DB_PATH=/data/sync_server.db`
4. Mount persistent volume at `/data`.
5. Health check path: `/health`.

Local Docker test:
```bash
docker build -f calcie_cloud/Dockerfile -t calcie-sync:latest .
docker run --rm -p 8000:8000 -e CALCIE_SYNC_DB_PATH=/data/sync_server.db calcie-sync:latest
```

Then point devices:
- laptop `.env`: `CALCIE_SYNC_BASE_URL=https://<your-backend-domain>`
- mobile `mobile_v1/.env`: `EXPO_PUBLIC_CALCIE_API_BASE_URL=https://<your-backend-domain>`

## 7) macOS permissions (required for real computer control)

Enable for the app that runs Python (`Terminal`, `iTerm`, or VS Code terminal host):

1. `System Settings -> Privacy & Security -> Accessibility` -> allow app
2. `System Settings -> Privacy & Security -> Screen Recording` -> allow app
3. Optional: `Input Monitoring` -> allow app
4. fully quit and reopen terminal app

## 8) Data and safety boundaries

Code safety:
- direct write command is blocked in code tools
- proposal/apply flow stores metadata and diffs in `.calcie/`

Sensitive reads:
- `.env` and selected sensitive files are blocked by code-tool read policy

Computer control:
- arm-lock prevents accidental clicks/types
- dry-run supports safe command testing

## 9) Troubleshooting

`IndentationError` or syntax startup errors:
- run:
```bash
python3 -m py_compile calcie.py
```

No voice input:
- install `speechrecognition`
- verify microphone permission for terminal app

No spoken output or weird pauses:
- edge-tts/network issues can fall back to `pyttsx3`
- tune:
  - `CALCIE_TTS_RATE`
  - `CALCIE_TTS_PITCH`
  - `CALCIE_TTS_VOICE`

Search gives weak results:
- ensure `TAVILY_API_KEY` or `EXA_API_KEY` exists
- check provider mode and fallback settings

Computer commands not executing:
- check `control status`
- if locked, run `control arm`
- if backend missing, install `pyautogui pillow`
- on macOS, verify Accessibility + Screen Recording permissions

Agentic plan quality issues:
- if planner emits weak/invalid actions, sanitizer now rewrites common mistakes
- set `CALCIE_COMPUTER_USE_PROVIDER=openai` (or `claude`) for stronger planning
- reduce step count with `CALCIE_COMPUTER_USE_MAX_STEPS=4` for tighter execution

Sync issues:
- set `CALCIE_SYNC_ENABLED=1` on participating devices
- use the same `CALCIE_SYNC_USER_ID` on laptop and mobile
- keep unique `CALCIE_DEVICE_ID` values (for example `laptop`, `mobile`)
- verify mobile can reach `CALCIE_SYNC_BASE_URL` over network

## 10) Security note

Do not commit real API keys to git.
Keep `.env` private, rotate exposed keys immediately, and prefer a `.env.example` for sharing config structure.

## 11) Quick command cookbook

General:
- `clear`
- `exit`

Search:
- `search latest ai funding news`
- `who won last night ipl`

Coding:
- `code tree`
- `code read calcie.py lines 1-120`
- `code propose calcie_core/skills/app_access.py :: improve youtube routing`

Apps/media:
- `open voice memos`
- `open amazon in chrome`
- `play music`
- `play blinding lights`
- `play video song perfect`

Agentic:
- `order a 72x60 mattress from amazon`
- `play one piece on netflix in chrome`
- `confirm`
- `cancel`
- `play music on mobile`
- `play music on laptop`

Computer:
- `control status`
- `control arm`
- `click at 720 510`
- `type hello`
- `press enter`
- `take screenshot dashboard`
- `control disarm`

---

If you keep only one doc open while building CALCIE, keep this one.
