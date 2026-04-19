# CALCIE Local API

Local HTTP control layer for desktop shells and background runtime use.

## Run

```bash
python3 -m calcie_local_api.server
```

## Default address

- `http://127.0.0.1:8765`

## Endpoints

- `GET /health`
- `GET /status`
- `GET /events`
- `POST /command`
- `POST /voice/start`
- `POST /voice/stop`
- `POST /vision/start`
- `POST /vision/stop`

## Notes

- This is intentionally local-only.
- It wraps the existing Python CALCIE runtime instead of replacing it.
- The macOS menu bar shell uses this API as its IPC boundary.
