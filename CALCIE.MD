
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
