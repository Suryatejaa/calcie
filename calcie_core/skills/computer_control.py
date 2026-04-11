"""Skill: local computer control (screenshot, click, scroll, type, keys)."""

import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

try:
    import pyautogui  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    pyautogui = None


class ComputerControlSkill:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.enabled = self._env_bool("CALCIE_COMPUTER_CONTROL_ENABLED", True)
        self.require_arm = self._env_bool("CALCIE_COMPUTER_REQUIRE_ARM", True)
        self.dry_run = self._env_bool("CALCIE_COMPUTER_DRY_RUN", False)
        self.arm_seconds = self._env_int("CALCIE_COMPUTER_ARM_SECONDS", 45, min_value=10, max_value=300)
        self.artifacts_dir = self.project_root / ".calcie" / "computer"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._armed_until = 0.0
        self._last_action_at = 0.0

    def handle_command(self, user_input: str) -> Tuple[Optional[str], Optional[str]]:
        raw = (user_input or "").strip()
        if not self._is_control_intent(raw):
            return None, None

        if not self.enabled:
            return (
                "Computer control is disabled. Set CALCIE_COMPUTER_CONTROL_ENABLED=1 to enable it.",
                "Computer control is disabled.",
            )

        normalized = raw.lower().strip()

        if re.match(r"^(?:computer|control)\s+help$", normalized):
            return self._help_text(), "Computer control help."

        if re.match(r"^(?:computer|control)\s+arm$", normalized):
            self._armed_until = time.time() + self.arm_seconds
            return (
                f"Computer control armed for {self.arm_seconds} seconds.",
                f"Computer control armed for {self.arm_seconds} seconds.",
            )

        if re.match(r"^(?:computer|control)\s+disarm$", normalized):
            self._armed_until = 0.0
            return "Computer control disarmed.", "Computer control disarmed."

        if re.match(r"^(?:computer|control)\s+status$", normalized):
            return self._status_text(), self._status_text()

        if re.match(r"^(?:computer|control)\s+(?:cursor|position|mouse\s+position)$", normalized):
            return self._cursor_position()

        if re.match(r"^(?:computer|control)\s+(?:screen\s+size|resolution|display)$", normalized):
            return self._screen_size()

        screenshot_match = re.match(
            r"^(?:computer\s+|control\s+)?(?:screenshot|take screenshot)(?:\s+(.+))?$",
            raw,
            flags=re.IGNORECASE,
        )
        if screenshot_match:
            label = (screenshot_match.group(1) or "").strip()
            return self._take_screenshot(label)

        if self.require_arm and not self._is_armed():
            return (
                "Computer control is locked. Run `control arm` first, then retry your action.",
                "Computer control is locked. Run control arm first.",
            )

        scroll_match = re.match(
            r"^(?:computer\s+|control\s+)?scroll\s+(up|down)(?:\s+(\d+))?$",
            normalized,
        )
        if scroll_match:
            direction = scroll_match.group(1)
            amount = int(scroll_match.group(2) or "600")
            delta = amount if direction == "up" else -amount
            return self._run_mouse_action(f"scroll {direction} {amount}", lambda: pyautogui.scroll(delta))

        click_match = re.match(
            r"^(?:computer\s+|control\s+)?click(?:\s+at)?\s+(\d+)\s+(\d+)$",
            normalized,
        )
        if click_match:
            x, y = int(click_match.group(1)), int(click_match.group(2))
            return self._run_mouse_action(f"click {x} {y}", lambda: pyautogui.click(x=x, y=y))

        dbl_match = re.match(
            r"^(?:computer\s+|control\s+)?double\s+click(?:\s+at)?\s+(\d+)\s+(\d+)$",
            normalized,
        )
        if dbl_match:
            x, y = int(dbl_match.group(1)), int(dbl_match.group(2))
            return self._run_mouse_action(f"double click {x} {y}", lambda: pyautogui.doubleClick(x=x, y=y))

        right_match = re.match(
            r"^(?:computer\s+|control\s+)?right\s+click(?:\s+at)?\s+(\d+)\s+(\d+)$",
            normalized,
        )
        if right_match:
            x, y = int(right_match.group(1)), int(right_match.group(2))
            return self._run_mouse_action(f"right click {x} {y}", lambda: pyautogui.rightClick(x=x, y=y))

        move_match = re.match(
            r"^(?:computer\s+|control\s+)?move(?:\s+mouse)?\s+(\d+)\s+(\d+)$",
            normalized,
        )
        if move_match:
            x, y = int(move_match.group(1)), int(move_match.group(2))
            return self._run_mouse_action(f"move mouse to {x} {y}", lambda: pyautogui.moveTo(x=x, y=y, duration=0.2))

        type_match = re.match(
            r"^(?:computer\s+|control\s+)?type\s+(.+)$",
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if type_match:
            text = type_match.group(1).strip().strip("\"'")
            if not text:
                return "Usage: type <text>", "Type command needs text."
            return self._run_mouse_action(f"type text ({len(text)} chars)", lambda: pyautogui.write(text, interval=0.02))

        press_match = re.match(
            r"^(?:computer\s+|control\s+)?press\s+([a-z0-9_+\- ]+)$",
            normalized,
        )
        if press_match:
            key = self._normalize_key_token(press_match.group(1).strip())
            return self._run_mouse_action(f"press {key}", lambda: pyautogui.press(key))

        hotkey_match = re.match(
            r"^(?:computer\s+|control\s+)?hotkey\s+([a-z0-9_+\- ]+)$",
            normalized,
        )
        if hotkey_match:
            raw_keys = hotkey_match.group(1).replace("-", "+")
            keys = [self._normalize_key_token(k.strip()) for k in raw_keys.split("+") if k.strip()]
            if not keys:
                return "Usage: hotkey <key1+key2+...>", "Hotkey command needs keys."
            label = "+".join(keys)
            return self._run_mouse_action(f"hotkey {label}", lambda: pyautogui.hotkey(*keys))

        return (
            "Unrecognized computer command. Run `control help` for supported actions.",
            "Unrecognized computer command.",
        )

    def _is_control_intent(self, text: str) -> bool:
        normalized = (text or "").strip().lower()
        if not normalized:
            return False
        if normalized.startswith("computer ") or normalized.startswith("control "):
            return True
        command_starts = (
            "screenshot",
            "take screenshot",
            "scroll ",
            "click ",
            "double click ",
            "right click ",
            "move ",
            "move mouse ",
            "type ",
            "press ",
            "hotkey ",
        )
        return normalized.startswith(command_starts)

    def _help_text(self) -> str:
        return (
            "Computer control commands:\n"
            "1. control help\n"
            "2. control status\n"
            "3. control arm\n"
            "4. control disarm\n"
            "5. screenshot [label]\n"
            "6. scroll up|down [amount]\n"
            "7. click <x> <y>\n"
            "8. click at <x> <y>\n"
            "9. double click <x> <y>\n"
            "10. right click <x> <y>\n"
            "11. move <x> <y>\n"
            "12. type <text>\n"
            "13. press <key>\n"
            "14. hotkey <key1+key2>\n"
            "15. control cursor (shows current pointer x,y)\n"
            "16. control screen size\n"
            "Safety: when arm-lock is enabled, run `control arm` before click/type/press actions."
        )

    def _status_text(self) -> str:
        armed = self._is_armed()
        backend = "pyautogui ready" if pyautogui is not None else "pyautogui missing"
        lock = "on" if self.require_arm else "off"
        dry = "on" if self.dry_run else "off"
        if armed:
            remaining = max(0, int(self._armed_until - time.time()))
            armed_text = f"armed ({remaining}s left)"
        else:
            armed_text = "disarmed"
        return f"Computer control: {armed_text} | arm-lock: {lock} | dry-run: {dry} | backend: {backend}"

    def _is_armed(self) -> bool:
        return time.time() < self._armed_until

    def _take_screenshot(self, label: str):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_label = re.sub(r"[^a-zA-Z0-9_-]+", "_", label).strip("_")
        suffix = f"_{safe_label}" if safe_label else ""
        out_path = self.artifacts_dir / f"screenshot_{stamp}{suffix}.png"

        if self.dry_run:
            return f"[DRY RUN] Screenshot would be saved to: {out_path}", "Dry run screenshot."

        try:
            if pyautogui is not None:
                image = pyautogui.screenshot()
                image.save(out_path)
                return f"Screenshot saved: {out_path}", "Screenshot captured."

            if sys.platform == "darwin":
                proc = subprocess.run(["screencapture", "-x", str(out_path)], capture_output=True, text=True)
                if proc.returncode == 0:
                    return f"Screenshot saved: {out_path}", "Screenshot captured."
                err = (proc.stderr or proc.stdout or "screencapture failed").strip()
                return f"Screenshot failed: {err}", "Screenshot failed."

            return "Screenshot backend unavailable. Install pyautogui + pillow for full support.", "Screenshot unavailable."
        except Exception as exc:
            return f"Screenshot failed: {exc}", "Screenshot failed."

    def _cursor_position(self):
        if self.dry_run:
            return "[DRY RUN] Cursor position query executed.", "Dry run cursor position."
        if pyautogui is None:
            return (
                "Cursor position requires `pyautogui`. Install dependencies and restart.",
                "Cursor position unavailable.",
            )
        try:
            x, y = pyautogui.position()
            return f"Cursor is at: {x}, {y}", f"Cursor position {x}, {y}."
        except Exception as exc:
            return f"Cursor position failed: {exc}", "Cursor position failed."

    def _screen_size(self):
        if self.dry_run:
            return "[DRY RUN] Screen size query executed.", "Dry run screen size."
        if pyautogui is None:
            return (
                "Screen size requires `pyautogui`. Install dependencies and restart.",
                "Screen size unavailable.",
            )
        try:
            width, height = pyautogui.size()
            return f"Screen size: {width}x{height}", f"Screen size {width} by {height}."
        except Exception as exc:
            return f"Screen size failed: {exc}", "Screen size failed."

    def _run_mouse_action(self, label: str, action):
        if self.dry_run:
            return f"[DRY RUN] Would execute: {label}", f"Dry run {label}."

        if pyautogui is None:
            return (
                "Computer action backend unavailable. Install `pyautogui` and `pillow`, then restart.",
                "Computer action backend unavailable.",
            )

        try:
            pyautogui.FAILSAFE = True
            action()
            self._last_action_at = time.time()
            return f"Executed: {label}", f"Done: {label}."
        except Exception as exc:
            return f"Action failed ({label}): {exc}", "Action failed."

    def _normalize_key_token(self, raw: str) -> str:
        token = (raw or "").strip().lower()
        mapping = {
            "cmd": "command",
            "command": "command",
            "ctrl": "ctrl",
            "control": "ctrl",
            "opt": "option",
            "alt": "alt",
            "return": "enter",
            "esc": "esc",
            "spacebar": "space",
            "pgup": "pageup",
            "pgdn": "pagedown",
            "del": "delete",
            "bksp": "backspace",
            "up": "up",
            "down": "down",
            "left": "left",
            "right": "right",
        }
        return mapping.get(token, token)

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
