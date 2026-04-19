# CALCIE Player Plan

## Goal

Build a **single controlled media surface** for CALCIE so media requests do not open random tabs, duplicate playback, or lose state across windows.

Target experience:
- `play perfect`
- `play video song perfect`
- `pause`
- `resume`
- `next`
- `previous`
- `set volume to 40`
- `set speed to 1.25`

CALCIE should control one playback surface instead of spawning multiple browser tabs.

Important UX constraint:
- the player should stay under the **CALCIE macOS shell**
- CALCIE must not open independent browser tabs for normal playback
- the player surface should be owned by the menu bar app

Platform split:
- **desktop/macOS** -> CALCIE-owned player surface
- **mobile OS** -> prefer native YouTube / YouTube Music apps
- avoid browser playback on mobile unless there is no better fallback

---

## Reality Check

This idea is strong, but a few parts are **not straightforward**:

### 1. Google login inside an embedded app is risky

Direct Gmail / Google Account login inside an embedded webview is often discouraged or blocked by Google auth policies.

So:
- **do not plan around “Google login inside embedded webview” as the core path**
- instead use:
  - external browser OAuth/login flow
  - or a dedicated persisted browser session

### 2. YouTube can be embedded more easily than YouTube Music

YouTube video playback is much easier to control with:
- YouTube embed / player APIs
- a controlled webview / browser surface

YouTube Music is harder because:
- it behaves more like a web app
- full embedding may be blocked or brittle
- playback control is not as clean as YouTube iframe player control

### 3. Full “CALCIE Player with YT Music + Gmail inside app” is a V2/V3 project

The safest and smartest first version is:
- **one dedicated CALCIE playback surface**
- **one session only**
- **one state manager**
- control commands routed into that surface

That alone solves most current pain.

---

## Recommended Strategy

Do this in phases.

### Phase 1: Single Playback Surface

Create a **CALCIE Player panel** as the only playback surface.

Behavior:
- If CALCIE receives a media request, it checks whether CALCIE Player is already active.
- If yes, reuse it.
- If not, open it.
- All new media commands update the same player surface.

This should be:
- a shell-owned media panel or popover
- hosted inside the CALCIE macOS app
- backed by a controlled webview or embedded player surface
- managed by CALCIE session state, not browser tabs

Primary goal:
- **never open multiple playback tabs/windows again**

### Phase 2: YouTube-first Controlled Playback

Use YouTube as the first integrated provider because it is easier to control.

For music requests:
- search YouTube
- prefer official audio/video results
- load selected video inside the CALCIE Player

For video song / general video:
- search YouTube
- load inside same player

This gives:
- play
- pause
- resume
- seek
- volume
- speed
- next/previous in a CALCIE-managed queue

### Phase 3: Account-aware Session

Instead of embedded Gmail login:
- ask the user to sign into Google in a **dedicated CALCIE browser/session flow**
- persist that session carefully
- reuse that session for search/history/recommendation continuity where possible

Safer options:
- external login handoff
- dedicated profile/session cookie jar
- avoid raw embedded Google auth inside a custom webview as the primary method

### Phase 4: YouTube Music Feasibility Layer

Only after Phase 1 and 2 are stable:
- test whether YouTube Music can be used in a controlled embedded/session-managed surface
- if not reliable, keep YouTube as playback engine for both songs and video songs

Important:
- do not block the whole player project on YT Music embedding

---

## Architecture

## A. Components

### 1. Media Intent Router

Responsibility:
- classify request into:
  - `music`
  - `video_song`
  - `youtube_video`
  - `generic_media_control`

Examples:
- `play perfect` -> `music`
- `play video song perfect` -> `video_song`
- `play lex fridman podcast on youtube` -> `youtube_video`
- `pause` -> `generic_media_control`

### 2. Media Session Manager

Responsibility:
- maintain single active playback session
- track:
  - provider
  - current media id/url
  - queue
  - playing/paused
  - position
  - volume
  - speed

This is the core fix for your current issue.

### 3. CALCIE Player UI

Responsibility:
- render player
- show current track/video
- accept internal control commands

Placement:
- inside the CALCIE macOS shell
- either:
  - a dedicated popover section
  - or a detachable CALCIE-owned player panel
- not a normal browser tab

Suggested controls:
- play/pause
- next
- previous
- seek
- volume slider
- speed selector
- queue list
- “open on YouTube” fallback button

### 4. YouTube Search Resolver

Responsibility:
- resolve user query into a playable YouTube video
- choose best candidate
- return:
  - title
  - video id
  - thumbnail
  - channel
  - duration

### 5. Provider Adapter Layer

Start with:
- `YouTubeProvider`

Later:
- `YouTubeMusicProvider` if feasible

Interface:
- `search(query)`
- `play(item)`
- `pause()`
- `resume()`
- `setVolume(v)`
- `setSpeed(v)`
- `next()`
- `previous()`

---

## Best Technical Direction

## Option 1: Menu Bar-Owned WebView Player

Build a CALCIE-owned player surface:
- Swift/AppKit shell
- embedded `WKWebView`
- YouTube embed player API inside that controlled surface

Pros:
- fast to build
- easy to iterate
- direct playback controls
- single session surface
- no stray browser tabs

Cons:
- YT Music embedding likely weak
- still subject to Google/webview auth limitations

### Recommendation
**Best V1**

## Option 2: Native Detached Player Window

Embed a `WKWebView` in a CALCIE-owned detachable player panel/window launched from the menu bar app.

Pros:
- feels more native
- one dedicated app window
- tighter app-level lifecycle
- better room for queue/progress/artwork UI

Cons:
- slightly more Swift/AppKit complexity
- Google auth limitations still apply

### Recommendation
**Best V1.5 / V2**

## Option 3: Browser-tab Control Only

Use one dedicated browser tab and control it via automation.

Pros:
- easier than full embedded app
- can reuse existing browser login

Cons:
- still browser-dependent
- less elegant
- more fragile than app-owned player

### Recommendation
Fallback only. Not the target architecture.

---

## Revised Recommendation

The player should live in the **CALCIE macOS shell**, not in a standalone browser tab.

Best path:
1. keep the menu bar app as the owner
2. add a **CALCIE Player popover section** first
3. if the popover is too small, evolve it into a **CALCIE-owned detached player panel**
4. keep browser usage only as a fallback escape hatch, not the main playback path

---

## Recommended Build Order

## Phase 1: Controlled YouTube Player

Deliverables:
- local player page
- one active playback surface
- one queue
- play/pause/resume/seek/volume/speed
- search -> choose best YouTube result -> play inside player

No YT Music yet.

### Definition of done
- `play perfect` reuses same player
- `play believer` replaces current item in same player
- `pause` pauses current player
- `resume` resumes same player
- no extra tabs/windows are opened

## Phase 2: Queue + Session State

Deliverables:
- queue management
- next/previous
- current track state persisted
- last player session recoverable

### Definition of done
- `next`
- `previous`
- resume after app restart

## Phase 3: Google Session Strategy

Deliverables:
- account/session decision
- dedicated login/session flow
- clear fallback if embedded login is blocked

### Definition of done
- stable logged-in continuity without relying on random browser windows

## Phase 4: Explore YT Music Integration

Deliverables:
- feasibility test
- if stable, provider adapter for YT Music
- if unstable, keep YouTube as music/video engine

### Definition of done
- only keep if truly reliable

---

## UI Plan

CALCIE Player should have:
- big artwork/thumbnail
- title
- channel/artist
- progress bar
- current time / total time
- play/pause
- next/previous
- volume slider
- speed menu
- queue panel
- status line:
  - `Playing from CALCIE Player`

Optional:
- lyrics button
- “open original page”

---

## Command Plan

Supported commands for V1:
- `play <song>`
- `play video song <name>`
- `play <video> on youtube`
- `pause`
- `resume`
- `stop`
- `next`
- `previous`
- `set volume to 40`
- `mute`
- `unmute`
- `set speed to 1.25`

Routing behavior:
- If CALCIE Player exists -> reuse it
- If not -> open it
- Never spawn a second playback session unless explicitly requested

---

## Data Model

Suggested session object:

```json
{
  "provider": "youtube",
  "player_mode": "audio|video",
  "current_item": {
    "id": "video_id",
    "title": "Perfect",
    "channel": "Ed Sheeran",
    "url": "https://youtube.com/watch?v=...",
    "thumbnail": "...",
    "duration_s": 263
  },
  "queue": [],
  "state": "playing|paused|stopped",
  "volume": 60,
  "speed": 1.0,
  "position_s": 0
}
```

---

## Risks

### Risk 1: Google auth restrictions

Mitigation:
- avoid depending on embedded Gmail login for V1

### Risk 2: YouTube Music embedding instability

Mitigation:
- use YouTube player as primary engine first

### Risk 3: Search quality for songs

Mitigation:
- use result ranking rules:
  - official audio/video
  - verified channel
  - high views
  - exact title match

### Risk 4: Queue/state drift

Mitigation:
- central session manager, not UI-managed state only

---

## Morning Implementation Plan

### Step 1
Add a **CALCIE Player surface** to the macOS shell:
- start with a player section in the menu bar popover
- if space is too tight, create a detachable CALCIE-owned player panel
- host playback in a controlled `WKWebView`

### Step 2
Add `MediaSessionManager` in Python:
- one active player
- queue/state methods

### Step 3
Add `YouTubeProvider` search + resolver

### Step 4
Add command routing:
- play/pause/resume/next/previous/volume/speed

### Step 5
Open and reuse exactly one CALCIE-owned player surface from the menu bar app

### Step 6
Test with:
- `play perfect`
- `play believer`
- `pause`
- `resume`
- `next`
- `set volume to 30`

### Step 7
Only after stable playback:
- evaluate account/session strategy
- then explore YT Music

---

## Phase 1 Deliverable (Updated)

Tomorrow’s goal should be:
- one **menu-bar-owned** CALCIE Player
- one playback session
- one queue
- zero extra browser tabs for normal media commands

That is the correct fix for the current duplication problem.

---

## Final Recommendation

Do **not** start with “embed Gmail + YT Music directly inside CALCIE.”

Start with:
- **single CALCIE-controlled YouTube player**
- **single session**
- **single queue**
- **full playback controls**

Platform policy:
- on **desktop**, keep playback inside CALCIE-owned UI
- on **mobile**, open the native YouTube / YT Music app instead of browser tabs/webviews
- this avoids duplicate browser playback surfaces on mobile where native apps already solve lifecycle and instance control better

That solves the current real problem:
- multiple tabs
- conflicting playback
- weak control

Then evolve toward:
- account-aware session
- optional YT Music support

That path is realistic, stable, and worth implementing.

---

## Mobile Decision

For mobile clients, do **not** build the same embedded CALCIE player first.

Preferred mobile behavior:
- `play <song>` -> open native **YouTube Music**
- `play video song <name>` -> open native **YouTube**
- `pause/resume/next/previous` -> if possible, route through mobile-native media/session controls

Why:
- native apps already manage playback lifecycle better on mobile
- duplicate app instances are much less of a problem than browser-tab duplication
- browser playback on mobile is the weaker UX and should stay fallback-only

So the strategy becomes:
- **desktop** = owned player
- **mobile** = native provider apps
