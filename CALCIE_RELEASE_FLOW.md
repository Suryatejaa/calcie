# CALCIE Dev -> Prod Release Flow

## Repository Model

CALCIE uses separate remotes for development, production app/backend code, and the public website.

Recommended local remotes:

```bash
./scripts/configure_release_remotes.sh
```

This configures:

```text
dev      https://github.com/Suryatejaa/calcie.git
prod     https://github.com/EchoLift/calcie.git
website  https://github.com/EchoLift/calcie-official.git
```

Use `dev` for active work and test deployments. Use `prod` only after release hygiene, build checks, and manual QA pass.

## Branch Model

```text
dev/main      active development and test builds
prod/prod     production release branch
website/main  public launch website deployed by Vercel
```

Promotion is one-way:

```text
local tested commit -> dev/main -> QA -> prod/prod
```

Do not develop directly on `prod/prod`.

## Backend Deployment

Development backend:
- deploy from dev repo/branch
- can use current Render/dev account
- uses staging secrets and staging DB

Production backend:
- deploy from `EchoLift/calcie`, branch `prod`
- Render production account
- production env vars only
- persistent DB/volume required

Important production env vars:

```text
CALCIE_SYNC_DB_PATH=/data/sync_server.db
CALCIE_CLOUD_ADMIN_TOKEN=<prod-admin-token>
```

If using Render with SQLite, mount persistent storage at `/data`.
Later, migrate to Postgres before larger public beta.

## Website Deployment

The public website lives in a separate repo:

```text
https://github.com/EchoLift/calcie-official.git
```

Export static site files:

```bash
./scripts/export_website.sh
```

The exported folder is:

```text
dist/calcie-official-site
```

Push that folder to the frontend repo, then connect Vercel to `EchoLift/calcie-official`.

Vercel should deploy:
- `index.html`
- `styles.css`
- `main.js`
- `docs/`
- `releases/`

## Release Checklist

1. Commit local changes.
2. Run hygiene:

```bash
./scripts/check_release_hygiene.py
```

3. Run promotion dry run:

```bash
./scripts/promote_calcie_prod.sh
```

4. Push to dev and test:

```bash
git push dev HEAD:main
```

5. Build DMG locally or in CI:

```bash
CALCIE_RELEASE_CHANNEL=alpha ./scripts/build_calcie_dmg.sh release
```

6. Upload DMG to the chosen download host.
7. Publish update manifest:

```bash
./scripts/publish_calcie_release.py \
  --download-url https://download-host/CALCIE-0.1.0-1-alpha.dmg \
  --release-notes-url https://calcie-site/releases/0.1.0
```

8. After QA, promote to production branch:

```bash
./scripts/promote_calcie_prod.sh --execute
```

The script asks for a second `promote` confirmation before pushing to `prod/prod`.

## CI/CD Direction

Dev CI should run:
- release hygiene
- Python compile/tests
- Swift build
- backend smoke tests

Prod CI should run:
- release hygiene
- backend deploy to Render prod
- DMG build/sign/notarize when certificates are available
- publish release metadata after DMG upload

Website CI should run:
- deploy static site to Vercel from `EchoLift/calcie-official`

## Safety Rules

Never ship:
- `.env`
- `.calcie/`
- `calcie_profile.local.json`
- `calcie_history.db`
- screen captures
- OCR dumps
- ChatGPT memory exports
- local ChromaDB data

Prod releases should be boring. Interesting things belong in dev until tested.
