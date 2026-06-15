**CALCIE current product state**

CALCIE is now in a real public **macOS alpha** state, not just a plan.

Current live surfaces:

- Website: `https://cacie-official.vercel.app/`
- Release notes: `https://cacie-official.vercel.app/releases/0.1.0`
- Public macOS alpha DMG: `https://pub-b83a9a395c1d450887d8e8bf992ee563.r2.dev/CALCIE-0.1.0-1-alpha.dmg`
- Cloud release metadata endpoint: `https://calcie.onrender.com/updates/releases`

That means CALCIE has crossed from prototype into testable product territory, even though it is still early and rough in a few important places.

---

**What CALCIE is right now**

```text
User downloads CALCIE alpha DMG
          ↓
Installs CALCIE.app into Applications
          ↓
If macOS blocks launch, user runs quarantine workaround
          ↓
CALCIE opens as a native macOS menu bar app
          ↓
Local CALCIE runtime handles:
  - chat
  - voice
  - vision
  - player
  - automation
          ↓
Cloud backend supports:
  - release metadata
  - update plumbing
  - backend/sync-style endpoints
```

So CALCIE is currently a **hybrid product**:

- **native macOS shell**
- **local assistant runtime**
- **cloud backend for release/update infrastructure**

It is not yet a fully sealed consumer desktop app with everything embedded and notarized.

---

**What is already working**

- native macOS menu bar shell
- typed command input
- voice push-to-talk using **hold Right Option**
- permissions checklist in the app
- launch-at-login
- CALCIE Player owned by the shell
- local HTTP control API between shell and runtime
- release website + setup docs + release notes
- public DMG hosting
- backend release manifest publishing
- first-run ChatGPT memory import path

This is enough for:
- alpha testers
- personal daily use
- early product feedback

---

**What is still alpha**

- macOS install trust flow is still rough
- the app is **not notarized**
- some users may see:
  - `CALCIE is damaged and can't be opened`
- current workaround after moving CALCIE into `Applications`:

```bash
xattr -dr com.apple.quarantine /Applications/CALCIE.app
```

- the local runtime is still closer to a repo-backed alpha runtime than a fully bundled consumer runtime
- Windows is still planned, not shipped
- offline local-model mode is still a product direction, not a finished launch feature

So the honest framing is:

**CALCIE is publicly downloadable, but still a hobby alpha rather than a polished mass-market desktop release.**

---

**Current architecture**

```text
macOS shell                -> calcie_macos/
local runtime              -> calcie.py + calcie_core/
local control API          -> calcie_local_api/
cloud backend              -> calcie_cloud/server.py
launch site/docs           -> static site on Vercel
download hosting           -> Cloudflare R2 public URL
```

In plain language:

- the **brain that actually does work** is still local
- the **menu bar experience** is native macOS
- the **cloud backend** helps with release/update plumbing and future sync/account paths

This is why backend deployment is done, but the DMG does **not** yet mean CALCIE is fully cloud-powered or fully self-contained.

---

**Current backend reality**

Backend is deployed.

Current live backend:
- `https://calcie.onrender.com`

What it is currently good for:
- release/update metadata
- sync/account foundation
- future paid/cloud mode plumbing

What it is **not** yet replacing:
- the local assistant runtime
- local voice/vision/control/player execution

So CALCIE is not “backend packed into the DMG.”
It is:
- **cloud-assisted**
- but still **local-runtime-first**

---

**Current macOS product reality**

CALCIE on macOS is now:

- a native menu bar app
- a floating `Settings` panel, not developer-style `Advanced Options`
- a reusable owned player surface
- a more user-facing shell with developer tools hidden by default in release builds

That means the product direction is now much clearer:

- users interact with CALCIE as an app
- terminal stays a developer surface
- local runtime continues doing the heavy lifting underneath

---

**Windows direction**

Windows is now important because many real testers are Windows-first.

We should not wait for perfect parity before supporting them.

The right Windows equivalent of the macOS menu bar shell is:

- **Windows system tray app**

not a giant desktop-first window.

That means the long-term product shape becomes:

```text
macOS   -> native menu bar app
Windows -> native tray app
Shared  -> Python runtime + local HTTP API + common product logic
```

The Windows rollout plan lives in:
- `CALCIE_WINDOWS_PLAN.md`

Recommended Windows posture:
- ship a **Windows beta**
- narrower scope than macOS at first
- use shared backend/runtime contract
- bring both platforms onto the same release rhythm later

---

**Offline / local model direction**

Offline mode still matters, but it should be treated as a staged product track, not something to block launch on.

The strongest future direction is:

- small local model for baseline reasoning
- structured memory/profile retrieval
- optional cloud upgrade for stronger/faster responses

This means CALCIE’s “brain” should eventually be:

```text
local symbolic memory
        +
local small model
        +
optional cloud model
```

not “LLM only” and not “cloud only.”

That is the right long-term product shape, but it is still ahead of the current alpha.

---

**What “production enough” means now**

For CALCIE, “production enough” should no longer mean “perfect.”
It should mean:

- public website is live
- users can actually download the app
- setup docs are honest
- runtime/app relationship is understandable
- permissions flow is acceptable
- update metadata exists
- alpha testers can succeed without hand-holding every single step

By that standard, CALCIE is **launchable as an alpha**.

It is **not yet production-polished** for mainstream public distribution because:

- no Apple notarization
- no fully bundled local runtime
- Windows not shipped yet

---

**Near-term priorities now**

The right next priorities are:

1. **alpha hardening**
   - fix rough onboarding edges
   - reduce remaining permission confusion
   - improve self-memory/profile responses

2. **Windows tray beta**
   - get Windows testers onto a real build
   - keep shared runtime/backend contract

3. **brain upgrade**
   - stronger local memory retrieval
   - persistent learned aliases/preferences
   - eventually optional offline local model

4. **better packaging later**
   - notarization when budget allows
   - more self-contained desktop distribution

---

**Recommended shipping sequence from here**

```text
1. Stabilize macOS alpha
2. Ship Windows tray beta
3. Improve local memory / "brain" quality
4. Make packaging more consumer-grade
5. Later add notarization and tighter offline model story
```

---

**Bottom line**

CALCIE is no longer just an internal build.

It is now:

- a live alpha product
- macOS-first
- local-runtime-first
- cloud-assisted
- Windows-next

The product question has shifted from:

- “Can we launch?”

to:

- “How do we harden the alpha, support Windows testers, and make CALCIE feel more like it truly has its own brain?”
