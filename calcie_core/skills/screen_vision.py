"""Skill: continuous screen monitoring with multimodal vision analysis."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

try:
    import pyautogui  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    pyautogui = None


class ScreenVisionSkill:
    def __init__(
        self,
        project_root: Path,
        analyze_image: Callable[[str, str], Dict],
        notify_user: Callable[[str], None],
        execute_action: Optional[Callable[[str], str]] = None,
        memory_pipeline=None,
    ):
        self.project_root = Path(project_root)
        self.analyze_image = analyze_image
        self.notify_user = notify_user
        self.execute_action = execute_action
        self.memory_pipeline = memory_pipeline

        self.enabled = self._env_bool("CALCIE_SCREEN_VISION_ENABLED", True)
        self.interval_s = self._env_int("CALCIE_SCREEN_VISION_INTERVAL_S", 12, 3, 300)
        self.keep_all_captures = self._env_bool("CALCIE_SCREEN_VISION_KEEP_ALL_CAPTURES", False)
        self.allow_actions = self._env_bool("CALCIE_SCREEN_VISION_ALLOW_ACTIONS", False)
        self.auto_hide_calcie_menu = self._env_bool("CALCIE_SCREEN_VISION_AUTO_HIDE_CALCIE_MENU", True)
        self.memory_background_enabled = self._env_bool("CALCIE_SCREEN_MEMORY_BACKGROUND_ENABLED", True)
        self.memory_keep_captures = self._env_bool("CALCIE_SCREEN_MEMORY_KEEP_CAPTURES", False)
        self.shell_state_max_age_s = float(
            (os.environ.get("CALCIE_SCREEN_VISION_SHELL_STATE_MAX_AGE_S") or "1.5").strip() or "1.5"
        )
        self.max_events = self._env_int("CALCIE_SCREEN_VISION_MAX_EVENTS", 30, 5, 200)
        self.notify_cooldown_s = self._env_int("CALCIE_SCREEN_VISION_NOTIFY_COOLDOWN_S", 45, 5, 600)

        self.vision_dir = self.project_root / ".calcie" / "vision"
        self.capture_dir = self.vision_dir / "captures"
        self.events_path = self.vision_dir / "events.jsonl"
        self.shell_window_state_path = self.project_root / ".calcie" / "runtime" / "macos_shell_window.json"
        self.shell_control_request_path = self.project_root / ".calcie" / "runtime" / "macos_shell_control.json"
        self.vision_dir.mkdir(parents=True, exist_ok=True)
        self.capture_dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._memory_stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._memory_worker: Optional[threading.Thread] = None
        self._goal = ""
        self._running = False
        self._memory_running = False
        self._last_result: Optional[Dict] = None
        self._events: List[Dict] = []
        self._last_alert_at = 0.0
        self._start_memory_background_loop_if_enabled()

    def handle_command(self, user_input: str) -> Tuple[Optional[str], Optional[str]]:
        raw = (user_input or "").strip()
        if not self._is_monitor_intent(raw):
            return None, None

        if not self.enabled:
            return (
                "Screen vision is disabled. Set CALCIE_SCREEN_VISION_ENABLED=1 to enable it.",
                "Screen vision is disabled.",
            )

        normalized = raw.lower().strip()

        if normalized in {"vision help", "monitor help", "screen help"}:
            return self._help_text(), "Screen vision help."

        if normalized in {"vision status", "monitor status", "screen status"}:
            status = self._status_text()
            return status, status

        if normalized in {"vision stop", "monitor stop", "stop monitor", "stop vision"}:
            return self._stop_monitor()

        if normalized in {"vision events", "monitor events", "screen events"}:
            return self._events_text(), "Screen vision events."

        interval_match = re.match(r"^(?:vision|monitor|screen)\s+interval\s+(\d+)$", normalized)
        if interval_match:
            value = int(interval_match.group(1))
            self.interval_s = max(3, min(300, value))
            return (
                f"Screen vision interval updated to {self.interval_s} seconds.",
                f"Screen vision interval {self.interval_s} seconds.",
            )

        once_goal = self._extract_once_goal(raw)
        if once_goal:
            return self._run_once(once_goal, source="manual")

        start_goal = self._extract_start_goal(raw)
        if start_goal:
            return self._start_monitor(start_goal)

        return self._help_text(), "Screen vision help."

    def is_vision_intent(self, text: str) -> bool:
        return self._is_monitor_intent(text)

    def _is_monitor_intent(self, text: str) -> bool:
        normalized = (text or "").strip().lower()
        if not normalized:
            return False
        starts = (
            "vision ",
            "monitor ",
            "screen monitor ",
            "watch my screen",
            "monitor my screen",
            "analyze my screen",
        )
        exact = {"vision", "monitor", "screen vision", "screen monitor"}
        return normalized in exact or normalized.startswith(starts)

    def _extract_once_goal(self, raw: str) -> Optional[str]:
        match = re.match(
            r"^(?:vision|monitor|screen)\s+(?:once|analyze|check)\s+(.+)$",
            raw.strip(),
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            return match.group(1).strip()
        return None

    def _extract_start_goal(self, raw: str) -> Optional[str]:
        patterns = [
            r"^(?:vision|monitor|screen)\s+start\s+(.+)$",
            r"^(?:watch|monitor)\s+my\s+screen\s+for\s+(.+)$",
            r"^(?:vision|monitor)\s+(.+)$",
        ]
        for pattern in patterns:
            match = re.match(pattern, raw.strip(), flags=re.IGNORECASE | re.DOTALL)
            if match:
                goal = match.group(1).strip()
                lowered = goal.lower()
                if lowered in {"help", "status", "stop", "events"}:
                    return None
                return goal
        return None

    def _help_text(self) -> str:
        return (
            "Screen vision commands:\n"
            "1. vision help\n"
            "2. vision status\n"
            "3. vision start <goal>\n"
            "4. vision once <goal>\n"
            "5. vision stop\n"
            "6. vision events\n"
            "7. vision interval <seconds>\n"
            "Examples:\n"
            "- vision start watch for build failures in the terminal\n"
            "- vision once check whether this dashboard shows a red alert\n"
            "- vision stop\n"
            "Default behavior is alert-only. Auto-actions stay off unless CALCIE_SCREEN_VISION_ALLOW_ACTIONS=1."
        )

    def _status_text(self) -> str:
        with self._lock:
            running = self._running
            goal = self._goal
            last_result = dict(self._last_result or {})
        state = "running" if running else "idle"
        pieces = [
            f"Screen vision: {state}",
            f"interval: {self.interval_s}s",
            f"actions: {'on' if self.allow_actions else 'off'}",
        ]
        if self.memory_pipeline and getattr(self.memory_pipeline, "enabled", False):
            memory_state = "running" if self._memory_running else "idle"
            memory_interval = getattr(self.memory_pipeline, "min_interval_s", "?")
            pieces.append(f"memory: {memory_state} every {memory_interval}s")
        if goal:
            pieces.append(f"goal: {goal}")
        if last_result:
            pieces.append(
                "last: "
                + str(last_result.get("summary") or last_result.get("alert_message") or "no summary")
            )
        return " | ".join(pieces)

    def _events_text(self) -> str:
        with self._lock:
            events = list(self._events[-8:])
        if not events:
            return "No screen vision events recorded yet."
        lines = ["Recent screen vision events:"]
        for event in reversed(events):
            stamp = event.get("timestamp", "?")
            severity = event.get("severity", "low")
            matched = "matched" if event.get("matched") else "clear"
            summary = event.get("summary") or event.get("alert_message") or "No summary"
            lines.append(f"- {stamp} | {severity} | {matched} | {summary}")
        return "\n".join(lines)

    def _start_monitor(self, goal: str) -> Tuple[str, str]:
        with self._lock:
            self._goal = goal
            already_running = self._running
        if already_running:
            return (
                f"Screen vision goal updated. I am now watching for: {goal}",
                "Screen vision goal updated.",
            )

        self._stop_event.clear()
        self._worker = threading.Thread(target=self._monitor_loop, daemon=True)
        with self._lock:
            self._running = True
        self._worker.start()
        return (
            f"Screen vision started. I will watch your screen every {self.interval_s} seconds for: {goal}",
            "Screen vision started.",
        )

    def _stop_monitor(self) -> Tuple[str, str]:
        self._stop_event.set()
        with self._lock:
            was_running = self._running
            self._running = False
            self._goal = ""
        if not was_running:
            return "Screen vision is already stopped.", "Screen vision already stopped."
        return "Screen vision stopped.", "Screen vision stopped."

    def _start_memory_background_loop_if_enabled(self) -> None:
        if not self.memory_pipeline:
            return
        if not getattr(self.memory_pipeline, "enabled", False):
            return
        if not self.memory_background_enabled:
            return
        self._memory_stop_event.clear()
        self._memory_worker = threading.Thread(target=self._memory_loop, daemon=True)
        with self._lock:
            self._memory_running = True
        self._memory_worker.start()

    def _memory_loop(self) -> None:
        while not self._memory_stop_event.is_set():
            self._run_memory_capture_tick()
            wait_seconds = max(10, int(getattr(self.memory_pipeline, "min_interval_s", 45) or 45))
            for _ in range(wait_seconds):
                if self._memory_stop_event.is_set():
                    break
                time.sleep(1)
        with self._lock:
            self._memory_running = False

    def _run_memory_capture_tick(self) -> None:
        ok, screenshot_path, error = self._capture_screenshot("memory")
        if not ok or not screenshot_path:
            self._record_event(
                {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "goal": "screen memory",
                    "matched": False,
                    "severity": "low",
                    "summary": f"Screen memory capture skipped: {error}",
                    "alert_message": "",
                    "should_act": False,
                    "action_command": "",
                    "action_result": "",
                    "evidence": [],
                    "screenshot_path": "",
                }
            )
            return
        memory_result = self._maybe_record_screen_memory(str(screenshot_path), source="memory_loop")
        if not self.memory_keep_captures:
            try:
                Path(screenshot_path).unlink(missing_ok=True)
            except Exception:
                pass
        if memory_result and not memory_result.get("skipped"):
            self._record_event(
                {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "goal": "screen memory",
                    "matched": bool(memory_result.get("ok")),
                    "severity": "low",
                    "summary": (
                        f"Screen memory saved {memory_result.get('saved', 0)} item(s)"
                        f" from {memory_result.get('app_name') or 'unknown app'}."
                    ),
                    "alert_message": "",
                    "should_act": False,
                    "action_command": "",
                    "action_result": "",
                    "evidence": [],
                    "screenshot_path": str(screenshot_path),
                    "memory_result": dict(memory_result),
                }
            )

    def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                goal = self._goal
            if goal:
                self._run_once(goal, source="loop")
            wait_seconds = max(1, self.interval_s)
            for _ in range(wait_seconds):
                if self._stop_event.is_set():
                    break
                time.sleep(1)
        with self._lock:
            self._running = False

    def _run_once(self, goal: str, source: str) -> Tuple[str, str]:
        normalized = self.run_once_result(goal, source=source)
        self._record_event(normalized)

        if normalized["matched"]:
            self._maybe_alert(normalized)
            self._maybe_act(normalized)
        elif source == "loop" and not self.keep_all_captures:
            try:
                screenshot_path = str(normalized.get("screenshot_path") or "").strip()
                if screenshot_path:
                    Path(screenshot_path).unlink(missing_ok=True)
            except Exception:
                pass

        if source == "manual":
            summary = normalized.get("summary") or normalized.get("alert_message") or "No clear issue detected."
            return (
                f"Screen analysis complete.\n"
                f"Goal: {goal}\n"
                f"Matched: {'yes' if normalized['matched'] else 'no'}\n"
                f"Severity: {normalized['severity']}\n"
                f"Summary: {summary}\n"
                f"Screenshot: {normalized.get('screenshot_path', '')}",
                "Screen analysis complete.",
            )
        return "Screen vision loop tick completed.", "Screen vision tick."

    def run_once_result(self, goal: str, source: str = "manual") -> Dict:
        ok, screenshot_path, error = self._capture_screenshot(source)
        if not ok or not screenshot_path:
            return {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "goal": goal,
                "matched": False,
                "severity": "medium",
                "summary": f"Screen capture failed: {error}",
                "alert_message": "",
                "should_act": False,
                "action_command": "",
                "action_result": "",
                "evidence": [],
                "screenshot_path": "",
            }

        try:
            result = self.analyze_image(str(screenshot_path), goal) or {}
        except Exception as exc:
            result = {
                "matched": False,
                "severity": "medium",
                "summary": f"Vision analysis failed: {exc}",
                "alert_message": "",
                "should_act": False,
                "action_command": "",
            }

        normalized = self._normalize_result(result, goal, str(screenshot_path))
        self._maybe_record_screen_memory(str(screenshot_path), source=source)
        return normalized

    def _maybe_record_screen_memory(self, screenshot_path: str, source: str) -> Optional[Dict]:
        if not self.memory_pipeline:
            return None
        try:
            memory_result = self.memory_pipeline.maybe_process_screenshot(
                screenshot_path=screenshot_path,
                source=source,
            )
        except Exception as exc:
            memory_result = {"ok": False, "reason": f"screen_memory_failed: {exc}"}
        if not memory_result or memory_result.get("skipped"):
            return memory_result
        with self._lock:
            if self._last_result is not None:
                self._last_result["memory_result"] = dict(memory_result)
        return memory_result

    def _capture_screenshot(self, label: str) -> Tuple[bool, Optional[Path], str]:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_label = re.sub(r"[^a-zA-Z0-9_-]+", "_", label).strip("_") or "monitor"
        out_path = self.capture_dir / f"{stamp}_{safe_label}.png"
        try:
            self._prepare_capture_surface()
            if pyautogui is not None:
                image = pyautogui.screenshot()
                image.save(out_path)
                return True, out_path, ""
            if sys.platform == "darwin":
                proc = subprocess.run(["screencapture", "-x", str(out_path)], capture_output=True, text=True)
                if proc.returncode == 0:
                    return True, out_path, ""
                return False, None, (proc.stderr or proc.stdout or "screencapture failed").strip()
            return False, None, "No screenshot backend available. Install pyautogui + pillow."
        except Exception as exc:
            return False, None, str(exc)

    def _prepare_capture_surface(self) -> bool:
        if sys.platform != "darwin":
            return False
        metadata = self._load_shell_window_metadata()
        if not metadata:
            return False
        if metadata.get("visible") and self.auto_hide_calcie_menu:
            if self._request_shell_panel_dismiss() and self._wait_for_shell_hidden(timeout_s=1.2):
                return True
            self._dismiss_calcie_menu()
            time.sleep(0.35)
            return self._wait_for_shell_hidden(timeout_s=0.6)
        return False

    def _load_shell_window_metadata(self) -> Optional[Dict]:
        if sys.platform != "darwin" or not self.shell_window_state_path.exists():
            return None
        try:
            payload = json.loads(self.shell_window_state_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not self._is_shell_metadata_fresh(payload):
            return None
        return payload

    def _dismiss_calcie_menu(self) -> None:
        try:
            if pyautogui is not None:
                pyautogui.press("esc")
                return
        except Exception:
            pass
        try:
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to key code 53',
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
        except Exception:
            return

    def _is_shell_metadata_fresh(self, payload: Dict) -> bool:
        raw = str(payload.get("updated_at") or "").strip()
        if not raw:
            return False
        try:
            normalized = raw.replace("Z", "+00:00")
            updated_at = datetime.fromisoformat(normalized)
        except Exception:
            return False
        now = datetime.now(updated_at.tzinfo) if updated_at.tzinfo else datetime.now()
        age = (now - updated_at).total_seconds()
        return age <= max(0.25, self.shell_state_max_age_s)

    def _request_shell_panel_dismiss(self) -> bool:
        try:
            payload = {
                "action": "dismiss_panel",
                "request_id": f"capture-{int(time.time() * 1000)}",
                "requested_at": datetime.now().isoformat(),
            }
            self.shell_control_request_path.parent.mkdir(parents=True, exist_ok=True)
            self.shell_control_request_path.write_text(
                json.dumps(payload, ensure_ascii=True),
                encoding="utf-8",
            )
            return True
        except Exception:
            return False

    def _wait_for_shell_hidden(self, timeout_s: float) -> bool:
        deadline = time.time() + max(0.1, timeout_s)
        while time.time() < deadline:
            metadata = self._load_shell_window_metadata()
            if metadata is None or not metadata.get("visible"):
                return True
            time.sleep(0.08)
        return False

    def _normalize_result(self, result: Dict, goal: str, screenshot_path: str) -> Dict:
        severity = str(result.get("severity") or "low").strip().lower()
        if severity not in {"low", "medium", "high"}:
            severity = "low"
        evidence = result.get("evidence")
        if not isinstance(evidence, list):
            evidence = []
        normalized = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "goal": goal,
            "matched": bool(result.get("matched")),
            "severity": severity,
            "summary": str(result.get("summary") or "").strip(),
            "alert_message": str(result.get("alert_message") or "").strip(),
            "should_act": bool(result.get("should_act")),
            "action_command": str(result.get("action_command") or "").strip(),
            "action_result": "",
            "evidence": [str(item).strip() for item in evidence if str(item).strip()][:6],
            "screenshot_path": screenshot_path,
        }
        with self._lock:
            self._last_result = dict(normalized)
        return normalized

    def _record_event(self, event: Dict) -> None:
        with self._lock:
            self._events.append(dict(event))
            self._events = self._events[-self.max_events :]
        try:
            with self.events_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=True) + "\n")
        except Exception:
            pass

    def _maybe_alert(self, event: Dict) -> None:
        now = time.time()
        if now - self._last_alert_at < self.notify_cooldown_s:
            return
        self._last_alert_at = now
        message = event.get("alert_message") or event.get("summary") or "Screen vision detected a matching event."
        try:
            self.notify_user(message)
        except Exception:
            pass

    def _maybe_act(self, event: Dict) -> None:
        if not self.allow_actions or not self.execute_action:
            return
        command = str(event.get("action_command") or "").strip()
        if not command:
            return
        lowered = command.lower()
        allowed_prefixes = ("control ", "computer ", "open ", "play ", "search ")
        if not lowered.startswith(allowed_prefixes):
            event["action_result"] = "Blocked unsafe vision action."
            return
        try:
            event["action_result"] = self.execute_action(command)
        except Exception as exc:
            event["action_result"] = f"Vision action failed: {exc}"

    def _env_bool(self, name: str, default: bool) -> bool:
        raw = (os.environ.get(name) or "").strip().lower()
        if not raw:
            return default
        return raw in {"1", "true", "yes", "on"}

    def _env_int(self, name: str, default: int, min_value: int, max_value: int) -> int:
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            return default
        return max(min_value, min(max_value, value))
