"""CALCIE Cloud Sync API (V1).

Run:
    uvicorn calcie_cloud.server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RegisterDeviceRequest(BaseModel):
    user_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    device_type: str = Field(default="unknown")
    label: str = Field(default="")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MessageRequest(BaseModel):
    user_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    content: str = Field(min_length=1)


class FactsRequest(BaseModel):
    facts: List[str] = Field(default_factory=list)


class CommandRequest(BaseModel):
    user_id: str = Field(min_length=1)
    from_device: str = Field(min_length=1)
    target_device: str = Field(min_length=1)
    content: str = Field(min_length=1)
    requires_confirm: bool = Field(default=False)


class CommandAckRequest(BaseModel):
    result: str = Field(default="")
    status: str = Field(default="done")


class SyncStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    user_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    device_type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    PRIMARY KEY (user_id, device_id)
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    user_id TEXT PRIMARY KEY,
                    facts_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    from_device TEXT NOT NULL,
                    target_device TEXT NOT NULL,
                    content TEXT NOT NULL,
                    requires_confirm INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    result TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def register_device(self, req: RegisterDeviceRequest):
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO devices (user_id, device_id, device_type, label, metadata_json, last_seen)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, device_id)
                DO UPDATE SET
                    device_type=excluded.device_type,
                    label=excluded.label,
                    metadata_json=excluded.metadata_json,
                    last_seen=excluded.last_seen
                """,
                (
                    req.user_id,
                    req.device_id,
                    req.device_type,
                    req.label,
                    json.dumps(req.metadata or {}),
                    _utc_now(),
                ),
            )
            conn.commit()

    def list_devices(self, user_id: str) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM devices WHERE user_id=? ORDER BY last_seen DESC",
                (user_id,),
            ).fetchall()
        out = []
        for row in rows:
            out.append(
                {
                    "user_id": row["user_id"],
                    "device_id": row["device_id"],
                    "device_type": row["device_type"],
                    "label": row["label"],
                    "metadata": json.loads(row["metadata_json"] or "{}"),
                    "last_seen": row["last_seen"],
                }
            )
        return out

    def add_message(self, req: MessageRequest) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO messages (user_id, device_id, role, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (req.user_id, req.device_id, req.role, req.content, _utc_now()),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_messages(self, user_id: str, limit: int = 50, after_id: int = 0) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM messages
                WHERE user_id=? AND id>?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, after_id, limit),
            ).fetchall()
        out = []
        for row in reversed(rows):
            out.append(
                {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "device_id": row["device_id"],
                    "role": row["role"],
                    "content": row["content"],
                    "created_at": row["created_at"],
                }
            )
        return out

    def set_facts(self, user_id: str, facts: List[str]):
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO facts (user_id, facts_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id)
                DO UPDATE SET
                    facts_json=excluded.facts_json,
                    updated_at=excluded.updated_at
                """,
                (user_id, json.dumps(facts), _utc_now()),
            )
            conn.commit()

    def get_facts(self, user_id: str) -> List[str]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT facts_json FROM facts WHERE user_id=?",
                (user_id,),
            ).fetchone()
        if not row:
            return []
        try:
            data = json.loads(row["facts_json"] or "[]")
            if isinstance(data, list):
                return [str(x) for x in data]
        except Exception:
            pass
        return []

    def create_command(self, req: CommandRequest) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO commands
                (user_id, from_device, target_device, content, requires_confirm, status, result, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'pending', '', ?, ?)
                """,
                (
                    req.user_id,
                    req.from_device,
                    req.target_device,
                    req.content,
                    1 if req.requires_confirm else 0,
                    _utc_now(),
                    _utc_now(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def poll_commands(self, user_id: str, device_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM commands
                WHERE user_id=? AND target_device=? AND status='pending'
                ORDER BY id ASC
                LIMIT ?
                """,
                (user_id, device_id, limit),
            ).fetchall()
        out = []
        for row in rows:
            out.append(
                {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "from_device": row["from_device"],
                    "target_device": row["target_device"],
                    "content": row["content"],
                    "requires_confirm": bool(row["requires_confirm"]),
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return out

    def ack_command(self, command_id: int, status: str, result: str):
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE commands
                SET status=?, result=?, updated_at=?
                WHERE id=?
                """,
                (status, result, _utc_now(), command_id),
            )
            conn.commit()


DB_PATH = Path(os.environ.get("CALCIE_SYNC_DB_PATH") or ".calcie/sync_server.db")
STORE = SyncStore(DB_PATH)

app = FastAPI(title="CALCIE Sync API", version="v1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True, "service": "calcie-sync", "ts": _utc_now()}


@app.post("/devices/register")
def register_device(req: RegisterDeviceRequest):
    STORE.register_device(req)
    return {"ok": True, "device_id": req.device_id}


@app.get("/devices")
def list_devices(user_id: str = Query(...)):
    return {"ok": True, "devices": STORE.list_devices(user_id)}


@app.post("/messages")
def add_message(req: MessageRequest):
    msg_id = STORE.add_message(req)
    return {"ok": True, "id": msg_id}


@app.get("/messages")
def list_messages(user_id: str = Query(...), limit: int = Query(50, ge=1, le=500), after_id: int = Query(0, ge=0)):
    return {"ok": True, "messages": STORE.list_messages(user_id=user_id, limit=limit, after_id=after_id)}


@app.get("/facts/{user_id}")
def get_facts(user_id: str):
    return {"ok": True, "facts": STORE.get_facts(user_id)}


@app.put("/facts/{user_id}")
def put_facts(user_id: str, req: FactsRequest):
    STORE.set_facts(user_id, req.facts)
    return {"ok": True, "count": len(req.facts)}


@app.post("/commands")
def create_command(req: CommandRequest):
    cmd_id = STORE.create_command(req)
    return {"ok": True, "id": cmd_id}


@app.get("/commands/poll")
def poll_commands(user_id: str = Query(...), device_id: str = Query(...), limit: int = Query(20, ge=1, le=100)):
    return {"ok": True, "commands": STORE.poll_commands(user_id=user_id, device_id=device_id, limit=limit)}


@app.post("/commands/{command_id}/ack")
def ack_command(command_id: int, req: CommandAckRequest):
    if req.status not in {"done", "failed", "skipped"}:
        raise HTTPException(status_code=400, detail="Invalid status")
    STORE.ack_command(command_id, req.status, req.result)
    return {"ok": True}

