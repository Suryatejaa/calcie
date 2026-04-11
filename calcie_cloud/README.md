# CALCIE Sync Backend (V1)

FastAPI backend for cross-device synchronization between laptop and mobile.

## Features
- device registration (`/devices/register`)
- shared message timeline (`/messages`)
- shared facts (`/facts/{user_id}`)
- cross-device command queue (`/commands`, `/commands/poll`, `/commands/{id}/ack`)

## Run locally
```bash
python3 -m pip install -r calcie_cloud/requirements.txt
python3 -m uvicorn calcie_cloud.server:app --host 0.0.0.0 --port 8000
```

## Default storage
- SQLite file at `.calcie/sync_server.db`
- override via `CALCIE_SYNC_DB_PATH`

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
