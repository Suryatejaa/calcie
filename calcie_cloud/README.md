# CALCIE Sync Backend (V1)

FastAPI backend for cross-device synchronization between laptop and mobile.

## Features
- device registration (`/devices/register`)
- shared message timeline (`/messages`)
- shared facts (`/facts/{user_id}`)
- cross-device command queue (`/commands`, `/commands/poll`, `/commands/{id}/ack`)
- user records (`/users`)
- update manifest publishing/checking (`/updates/releases`, `/updates/latest`)
- user feedback (`/feedback`)
- crash reports (`/crashes`)

## Run locally
```bash
python3 -m pip install -r calcie_cloud/requirements.txt
python3 -m uvicorn calcie_cloud.server:app --host 0.0.0.0 --port 8000
```

## Default storage
- SQLite file at `.calcie/sync_server.db`
- override via `CALCIE_SYNC_DB_PATH`

## Production-facing endpoints

### Users
```bash
curl -X POST http://127.0.0.1:8000/users \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"local-user","display_name":"CALCIE User","metadata":{"channel":"alpha"}}'
```

### Update manifest
Publish a macOS release:

```bash
curl -X POST http://127.0.0.1:8000/updates/releases \
  -H 'Content-Type: application/json' \
  -H "x-calcie-admin-token: $CALCIE_CLOUD_ADMIN_TOKEN" \
  -d '{
    "platform": "macos",
    "channel": "alpha",
    "version": "0.1.0",
    "build": "1",
    "download_url": "https://example.com/CALCIE.dmg",
    "sha256": "replace-with-real-sha256",
    "release_notes_url": "https://example.com/releases/0.1.0",
    "minimum_os": "13.0",
    "required": false
  }'
```

Check latest release:

```bash
curl 'http://127.0.0.1:8000/updates/latest?platform=macos&channel=alpha'
```

If `CALCIE_CLOUD_ADMIN_TOKEN` is unset, release publishing is open for local/dev use.
Set it in production.

### Feedback
```bash
curl -X POST http://127.0.0.1:8000/feedback \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"local-user","category":"bug","message":"Something went wrong","app_version":"0.1.0"}'
```

### Crash reports
```bash
curl -X POST http://127.0.0.1:8000/crashes \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"local-user","device_id":"mac","app_version":"0.1.0","crash_type":"runtime","summary":"Runtime exited unexpectedly"}'
```

## Production note
You mentioned Supabase/Mongo Atlas. V1 is storage-agnostic at architecture level:
- keep this API contract stable
- replace `SyncStore` implementation in `server.py` with Supabase/Mongo-backed store
- clients (desktop/mobile) can remain unchanged

## Deploy now (Docker, easiest)
This repo now includes `calcie_cloud/Dockerfile`.

### 1) Build and test image locally
```bash
docker build -f calcie_cloud/Dockerfile -t calcie-sync:latest .
docker run --rm -p 8000:8000 -e CALCIE_SYNC_DB_PATH=/data/sync_server.db calcie-sync:latest
```
Check:
```bash
curl http://127.0.0.1:8000/health
```

### 2) Deploy to any Docker host (Render/Railway/Fly/EC2)
Use:
- Dockerfile path: `calcie_cloud/Dockerfile`
- start command: auto from Docker CMD
- health check path: `/health`
- env var:
  - `CALCIE_SYNC_DB_PATH=/data/sync_server.db`

### 3) Persistence (important)
Mount a persistent volume at `/data` in your host.
If you do not mount a volume, SQLite data resets on redeploy/restart.
