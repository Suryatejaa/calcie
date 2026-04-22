# CALCIE Deployment + CI/CD Plan

## Goal

Ship CALCIE as a production-ready local-first assistant with:
- a signed macOS app distributed as a DMG
- a backend for account/device sync, update manifests, feedback, and optional memory sync
- a database with user/device/release state
- an official website with downloads and docs
- safe update notifications
- no developer-specific Surya profile or local memory bundled into releases

CALCIE should install as a fresh assistant for each user, then invite them to import personal context explicitly.

## Product Boundary

CALCIE remains local-first by default.

The macOS app owns:
- menu bar companion UI
- push-to-talk hotkey
- CALCIE Player window
- runtime lifecycle
- local permissions onboarding
- update notifications

The Python runtime owns:
- routing and skills
- LLM/STT/TTS
- screen vision and screen memory
- local profile and memory storage
- local API used by the macOS app

The cloud backend owns only things that need a server:
- user account/session metadata
- device registration
- update manifest
- release channels
- optional encrypted sync metadata
- feedback/crash reports
- docs/download redirects

## Release Tracks

1. Local dev
- Runs from repo.
- Uses `.env`, local Python, local Swift build.
- Debug terminal remains available.

2. Private alpha
- Signed app installed from DMG.
- Backend deployed but minimal.
- Users manually grant macOS permissions.
- Updates can be announced but not auto-applied yet.

3. Public beta
- Signed + notarized DMG.
- Website download page live.
- Backend update manifest live.
- Clear onboarding, docs, privacy notes, and uninstall instructions.

4. Stable
- Automatic update channel or guided update flow.
- Crash/feedback pipeline.
- Migration scripts for local profile/memory schema.

## Backend Plan

Create a production backend service for:
- `POST /auth/session` or OAuth callback handling
- `POST /devices/register`
- `GET /updates/latest?platform=macos&channel=stable`
- `POST /feedback`
- `POST /crashes`
- optional `POST /sync/events`
- optional `GET /sync/events`

Recommended initial backend stack:
- API: existing Python/FastAPI style service
- DB: Postgres
- Object storage: release artifacts, logs, public docs assets if needed
- Secrets: provider-managed secret store, not `.env` committed into repo

Initial database tables:
- `users`
- `devices`
- `sessions`
- `release_channels`
- `release_artifacts`
- `update_checks`
- `feedback`
- `crash_reports`
- `sync_events` optional
- `memory_imports` optional metadata only, not raw private memory by default

## DMG + macOS Release Pipeline

Build output should be deterministic:
- build Swift package
- assemble `CALCIE.app`
- embed required runtime metadata
- code sign app bundle
- create DMG
- sign DMG
- notarize DMG
- staple notarization ticket
- upload DMG artifact
- update backend release manifest

Release manifest should include:
- version
- build number
- channel
- minimum macOS version
- download URL
- SHA256 checksum
- release notes URL
- required migration notes
- whether update is required or optional

## CI/CD Pipeline

Use GitHub Actions or equivalent with these jobs.

1. Python validation
- install Python deps
- run syntax checks
- run unit tests
- run route/skill smoke tests
- verify no `.env`, `.calcie`, captures, local DBs, or personal profile data are included

2. Swift validation
- `swift build`
- optional UI smoke build
- verify bundle metadata

3. Backend validation
- run backend tests
- run DB migrations against test DB
- check OpenAPI contract if added

4. Package macOS
- build `CALCIE.app`
- sign with Apple Developer certificate
- create signed DMG
- notarize and staple
- upload artifact

5. Publish release
- create GitHub release or storage artifact
- update backend release manifest
- deploy website/docs
- notify beta channel if enabled

Secrets needed in CI:
- Apple Developer certificate/password
- Apple notary credentials
- backend deploy token
- database migration URL
- release storage token
- website deploy token

## Website + Docs

Launch a small official site first, not a giant app portal.

Pages:
- Home: what CALCIE does
- Download: latest macOS DMG
- Setup: permissions checklist
- Docs: voice commands, screen memory, CALCIE Player, troubleshooting
- Privacy: local-first defaults, what leaves the device, how to delete data
- Release notes
- Contact/feedback

Docs must clearly explain:
- microphone permission
- accessibility permission
- screen recording permission
- notification permission
- where local data lives
- how to reset memory/profile
- how to uninstall

## Update Notifications

Start with safe update notifications before auto-update.

Flow:
- CALCIE checks backend update manifest on launch and periodically.
- If a newer version exists, menu bar shows `Update available`.
- Advanced window shows version, release notes, and download button.
- No forced auto-update in alpha.

Later:
- add automatic updater only after signing/notarization is stable.

## First-Run Personal Context Import

Do not ship any Surya/developer profile.

On first launch, CALCIE should show an optional onboarding step:

1. Explain: `CALCIE can work with no imported memory. If you want continuity from ChatGPT, you can manually export what ChatGPT knows about you and paste it here.`
2. Show copy button for this prompt:

```text
Return everything you know about me inside one fenced code block. Include long-term memory, bio details, and any model-set context you have with dates when available. I want a thorough memory export of what you've learned about me. Skip tool details and include only information that is actually about me. Be exhaustive and careful.
```

3. User pastes ChatGPT response into CALCIE.
4. CALCIE extracts only the fenced code block.
5. CALCIE asks the user to confirm import.
6. CALCIE stores parsed profile locally.
7. CALCIE provides `Delete imported memory` and `Re-import` controls.

Storage rules:
- Imported memory stays local by default.
- Do not upload raw imported memory unless user enables sync explicitly.
- Store source metadata: `source=chatgpt_manual_export`, `imported_at`, `user_confirmed=true`.

## Privacy + Safety Defaults

Release builds must not include:
- `.env`
- `.calcie/`
- screen captures
- OCR text dumps
- local ChromaDB data
- `calcie_history.db`
- personal `calcie_profile.local.json`
- developer-only runtime logs

Screen memory defaults for public beta:
- off by default, or clearly opt-in
- local-only by default
- visible status indicator
- easy pause/stop/delete

Automation defaults:
- destructive actions require confirmation
- payments/orders stop at review/cart stage
- vision auto-actions disabled unless user enables them

## Surya Profile Removal Checklist

- Replace hardcoded `Surya` assistant prompts with generic user language.
- Keep developer signing IDs separate from user profile data.
- Replace mobile default user ID `surya` with `local-user` or require explicit config.
- Convert root `calcie_profile.json` into a generic template.
- Keep personal profile in ignored local files only if needed.
- Ensure `.calcie/`, `.env`, local DBs, captures, and local profile files are ignored.
- Add CI check that fails if release artifacts contain private profile/capture files.

## Milestones

### Milestone 0: Repo Sanitization
- Remove developer profile defaults.
- Add profile template.
- Add packaging ignore checks.
- Verify clean install has no Surya-specific memory.

### Milestone 1: Backend Foundation
- Deploy backend service.
- Add Postgres migrations.
- Add device registration and update manifest endpoints.

### Milestone 2: App Release Build
- Stabilize app bundle build script.
- Add code signing and notarization pipeline.
- Produce first internal DMG.

### Milestone 3: Website + Docs
- Publish download page.
- Publish setup docs and privacy page.
- Link release notes from update manifest.

### Milestone 4: Update Notifications
- App checks manifest.
- Menu bar shows update availability.
- User can open release notes/download page.

### Milestone 5: First-Run Onboarding
- Add welcome screen.
- Add ChatGPT memory import prompt.
- Add paste/confirm/delete flow.

### Milestone 6: Private Alpha
- Ship to first testers.
- Collect install issues, permission issues, crash reports, and update friction.
