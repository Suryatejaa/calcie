"""Local HTTP control API for CALCIE desktop shells."""

from __future__ import annotations

import contextlib
import os
import sys
import threading
import time
import uuid
from typing import Any, Dict, List

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from calcie import Calcie


class CommandRequest(BaseModel):
    text: str = Field(min_length=1)


class VisionRequest(BaseModel):
    goal: str = Field(min_length=1)


class DesktopRuntime:
    def __init__(self):
        self.calcie = Calcie()
        self._lock = threading.Lock()
        self._voice_thread: threading.Thread | None = None
        self._voice_cancel_requested = False
        self.instance_id = uuid.uuid4().hex
        self.started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.api_version = "0.2.0"

    @contextlib.contextmanager
    def _suppress_terminal_io(self):
        with open(os.devnull, "w") as devnull:
            with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
                yield

    def _runtime_metadata(self) -> Dict[str, Any]:
        return {
            "runtime_instance_id": self.instance_id,
            "runtime_pid": os.getpid(),
            "runtime_started_at": self.started_at,
            "runtime_project_root": str(self.calcie.project_root),
            "runtime_api_version": self.api_version,
        }

    def health(self) -> Dict[str, Any]:
        payload = {"ok": True, "state": self.calcie.get_runtime_status().get("state", "unknown")}
        payload.update(self._runtime_metadata())
        return payload

    def status(self) -> Dict[str, Any]:
        status = self.calcie.get_runtime_status()
        status["voice_session_active"] = bool(self._voice_thread and self._voice_thread.is_alive())
        status["voice_cancel_requested"] = bool(self._voice_cancel_requested)
        status.update(self._runtime_metadata())
        return status

    def events(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self.calcie.get_recent_events(limit=limit)

    def command(self, text: str) -> Dict[str, Any]:
        try:
            with self._lock:
                with self._suppress_terminal_io():
                    response = self.calcie.chat(text)
                status = self.calcie.get_runtime_status()
        except Exception as exc:
            self.calcie._set_runtime_state("error", "Command execution failed")
            self.calcie._record_runtime_event("error", f"Command failed: {exc}", severity="high", state="error")
            return {
                "ok": False,
                "response": f"Command failed: {exc}",
                "spoken": "",
                "route": "",
                "state": "error",
            }
        return {
            "ok": True,
            "response": response,
            "spoken": response,
            "route": status.get("last_route", ""),
            "state": status.get("state", "idle"),
        }

    def start_vision(self, goal: str) -> Dict[str, Any]:
        with self._lock:
            response, spoken = self.calcie._handle_vision_command(f"vision start {goal}")
            status = self.calcie.get_runtime_status()
        return {
            "ok": response is not None,
            "response": response or "",
            "spoken": spoken or response or "",
            "state": "vision_monitoring" if status.get("vision_running") else status.get("state", "idle"),
        }

    def stop_vision(self) -> Dict[str, Any]:
        with self._lock:
            response, spoken = self.calcie._handle_vision_command("vision stop")
            status = self.calcie.get_runtime_status()
        return {
            "ok": response is not None,
            "response": response or "",
            "spoken": spoken or response or "",
            "state": status.get("state", "idle"),
        }

    def start_voice(self) -> Dict[str, Any]:
        if self._voice_thread and self._voice_thread.is_alive():
            return {"ok": True, "response": "Voice capture already active.", "state": "listening"}

        self._voice_cancel_requested = False
        self.calcie._set_runtime_state("listening", "Listening for voice input")
        self.calcie._record_runtime_event("voice", "Voice capture started", severity="low", state="listening")

        def _worker():
            try:
                text = self.calcie.listen_voice()
                if self._voice_cancel_requested:
                    self.calcie._record_runtime_event("voice", "Voice capture canceled", severity="low", state="idle")
                    self.calcie._set_runtime_state("idle", "Ready")
                    return
                if text:
                    with self._lock:
                        with self._suppress_terminal_io():
                            self.calcie.chat(text)
                else:
                    self.calcie._set_runtime_state("idle", "Ready")
            except Exception as exc:
                self.calcie._set_runtime_state("error", "Voice session failed")
                self.calcie._record_runtime_event("error", f"Voice session failed: {exc}", severity="high", state="error")

        self._voice_thread = threading.Thread(target=_worker, daemon=True)
        self._voice_thread.start()
        return {"ok": True, "response": "Voice capture started.", "state": "listening"}

    def stop_voice(self) -> Dict[str, Any]:
        self._voice_cancel_requested = True
        self.calcie._set_runtime_state("idle", "Ready")
        self.calcie._record_runtime_event(
            "voice",
            "Voice stop requested. Current recognition pass will end naturally.",
            severity="low",
            state="idle",
        )
        return {
            "ok": True,
            "response": "Voice stop requested. The current recognition pass will stop after the active listen cycle.",
            "state": "idle",
        }

    def restart(self) -> Dict[str, Any]:
        self.calcie._record_runtime_event("runtime", "Runtime restart requested", severity="medium", state="starting")

        def _restart_worker():
            time.sleep(0.5)
            os.execve(sys.executable, [sys.executable, "-m", "calcie_local_api.server"], os.environ.copy())

        threading.Thread(target=_restart_worker, daemon=True).start()
        return {
            "ok": True,
            "response": "Runtime restart requested.",
            "state": "starting",
        }


runtime = DesktopRuntime()

app = FastAPI(title="CALCIE Local API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1", "http://localhost"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def get_health():
    return runtime.health()


@app.get("/status")
def get_status():
    return runtime.status()


@app.get("/events")
def get_events(limit: int = 20):
    return {"ok": True, "events": runtime.events(limit=limit)}


@app.post("/command")
def post_command(req: CommandRequest):
    return runtime.command(req.text)


@app.post("/voice/start")
def post_voice_start():
    return runtime.start_voice()


@app.post("/voice/stop")
def post_voice_stop():
    return runtime.stop_voice()


@app.post("/vision/start")
def post_vision_start(req: VisionRequest):
    return runtime.start_vision(req.goal)


@app.post("/vision/stop")
def post_vision_stop():
    return runtime.stop_vision()


@app.post("/runtime/restart")
def post_runtime_restart():
    return runtime.restart()


def main():
    host = (os.environ.get("CALCIE_LOCAL_API_HOST") or "127.0.0.1").strip()
    port_raw = (os.environ.get("CALCIE_LOCAL_API_PORT") or "8765").strip()
    access_log = (os.environ.get("CALCIE_LOCAL_API_ACCESS_LOG", "0").strip().lower() in {"1", "true", "yes", "on"})
    log_level = (os.environ.get("CALCIE_LOCAL_API_LOG_LEVEL") or "warning").strip().lower()
    try:
        port = int(port_raw)
    except ValueError:
        port = 8765
    uvicorn.run(app, host=host, port=port, reload=False, access_log=access_log, log_level=log_level)


if __name__ == "__main__":
    main()
