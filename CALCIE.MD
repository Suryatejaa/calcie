
**The commercial CALCIE stack:**

```
User installs CALCIE.app (mac) / CALCIE.exe (windows)
          ↓
On first launch → Setup wizard
          ↓
┌─────────────────────────────────┐
│  Choose your AI mode:           │
│  ○ Cloud (recommended)          │
│    - Fast, always updated       │
│    - Needs internet             │
│    - Free tier + paid plans     │
│                                 │
│  ○ Offline (optional)           │
│    - Private, no internet       │
│    - Needs Ollama installed     │
│    - CALCIE will guide you      │
└─────────────────────────────────┘
```

---

**Offline onboarding flow CALCIE handles automatically:**

```
User selects offline mode
        ↓
CALCIE checks: is Ollama installed?
        ↓ No
"Let me help you set that up"
CALCIE opens: https://ollama.com/download
        ↓
CALCIE polls until Ollama is detected on :11434
        ↓
"Great, Ollama is running. Now downloading
 the AI model (4GB, one time only)..."
CALCIE runs: ollama pull llama3.2
        ↓
Progress bar in CALCIE UI
        ↓
"You're all set. CALCIE is now fully offline."
```

This is exactly what apps like LM Studio, Jan, and Msty do. Users don't need to touch a terminal.

---

**Commercial tier structure this enables:**

| Plan | LLM | Search | Price |
|---|---|---|---|
| Free | Offline Ollama only | Limited | $0 |
| Pro | Gemini/Claude/GPT-4 | Full | $8-12/month |
| Teams | All providers + shared memory | Full + collab | $20+/month |

The offline tier is your **free acquisition channel** — zero cloud cost for you, full privacy for them. Users who want faster/smarter responses upgrade to Pro.

---

**What this means for your backend:**

```
Free/Offline users  →  No backend calls at all
                        CALCIE runs 100% local
                        Zero cost to you

Pro users           →  calcie_cloud/server.py
                        LLM API calls (you pay wholesale, charge retail)
                        Sync across devices
```

Render free tier handles the sync backend for Pro users fine at small scale. When you grow, move to a $7/month VPS — not a GPU instance, just a basic compute node.

---

**The Ollama model recommendation for users:**

| Use case | Model | Size | Why |
|---|---|---|---|
| Default offline | `llama3.2:3b` | 2GB | Fast, works on 8GB RAM |
| Better quality | `llama3.2` | 4GB | Good balance |
| Best offline | `gemma4:e2b` | ~3GB | Best reasoning at this size |
| Low end devices | `phi3:mini` | 2.3GB | Works on 4GB RAM |

CALCIE auto-detects RAM and recommends the right model during setup.

---

**Deployment order now:**

We should ship in this order instead of trying to launch everything at once:

### Phase 1: backend first

Ship `calcie_cloud/server.py` as the first stable public service.

Purpose:
- account/session layer for Pro users
- sync across devices
- usage/auth foundation for later billing
- stable API base before public downloads

Recommended first host:
- Render or Railway for the first public version
- move to a small VPS later if usage grows

Exit criteria:
- health check + uptime monitoring
- production env vars
- auth/account model decided
- logs + error reporting
- stable public base URL

### Phase 2: signed macOS app + DMG

After backend is stable, ship the macOS installer path:

- `CALCIE.app`
- signed build
- DMG installer

The DMG should include:
- CALCIE.app
- Applications shortcut
- short install instructions

Exit criteria:
- stable signing identity
- packaged app launches without Xcode/Terminal
- permissions/onboarding are acceptable
- DMG install flow is clean enough for non-technical users

### Phase 3: official website + docs

Once backend and DMG are stable, publish the public web layer:

- landing page
- download page for macOS
- docs
- pricing / free-vs-pro explanation
- offline-vs-cloud onboarding explanation

Website sections should be minimal first:
- Home
- Download
- Docs
- Pricing
- Privacy

Docs should cover:
- install CALCIE on macOS
- permissions
- offline Ollama setup
- cloud mode setup
- common troubleshooting

### Phase 4: Windows `.exe` later

Windows should stay deliberately later.

Reason:
- packaging
- code signing
- audio/hotkey/system-permission behavior
- installer support burden

Do not block the public macOS launch on Windows.

---

**Recommended shipping sequence:**

```text
1. Deploy backend
2. Package signed CALCIE.app
3. Build DMG
4. Launch official website
5. Publish docs
6. Ship Windows .exe later
```

---

**What “production ready enough” means before public launch:**

- backend has a stable URL
- macOS app installs from DMG
- permissions are understandable
- update path is defined
- website explains offline vs cloud clearly
- docs answer setup questions without needing us directly

---

**Near-term focus:**

The music player is already good enough for now.

So the next product work should move away from feature depth and into:
- backend deployment
- macOS packaging/distribution
- website
- docs
- launch readiness
