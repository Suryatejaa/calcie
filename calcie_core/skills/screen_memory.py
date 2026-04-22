"""Screen memory pipeline: screenshot OCR -> LLM extraction -> deduped storage."""

from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


class ScreenMemoryPipeline:
    def __init__(
        self,
        project_root: Path,
        llm_collect_text: Callable[..., str],
    ):
        self.project_root = Path(project_root)
        self.llm_collect_text = llm_collect_text
        self.enabled = self._env_bool("CALCIE_SCREEN_MEMORY_ENABLED", False)
        self.min_interval_s = self._env_int("CALCIE_SCREEN_MEMORY_INTERVAL_S", 45, 10, 600)
        self.max_ocr_chars = self._env_int("CALCIE_SCREEN_MEMORY_MAX_OCR_CHARS", 6000, 800, 30000)
        self.max_existing_docs = self._env_int("CALCIE_SCREEN_MEMORY_JSONL_DEDUP_SCAN", 250, 20, 2000)
        self.idle_skip_s = self._env_int("CALCIE_SCREEN_MEMORY_SKIP_IDLE_S", 300, 30, 3600)
        self.dedup_threshold = self._env_float("CALCIE_SCREEN_MEMORY_DEDUP_THRESHOLD", 0.15, 0.01, 0.8)
        self.provider = (os.environ.get("CALCIE_SCREEN_MEMORY_LLM_PROVIDER") or "gemini").strip().lower()
        self.store_backend = (os.environ.get("CALCIE_SCREEN_MEMORY_STORE") or "auto").strip().lower()
        self.memory_dir = self.project_root / ".calcie" / "screen_memory"
        self.memory_jsonl = self.memory_dir / "memories.jsonl"
        self.activity_jsonl = self.memory_dir / "activity.jsonl"
        self.ocr_dir = self.memory_dir / "ocr"
        self.vision_ocr_script = self.project_root / "scripts" / "apple_vision_ocr.swift"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.ocr_dir.mkdir(parents=True, exist_ok=True)
        self._last_run_at = 0.0
        self._chroma_collection = None
        self._chroma_error = ""

    def maybe_process_screenshot(self, screenshot_path: str, source: str = "vision") -> Dict:
        if not self.enabled:
            return {"ok": False, "skipped": True, "reason": "disabled"}

        now = time.time()
        if now - self._last_run_at < self.min_interval_s:
            return {"ok": False, "skipped": True, "reason": "cooldown"}

        app_name = self._frontmost_app_name()
        if self._should_skip_for_idle_or_lock(app_name):
            return {"ok": False, "skipped": True, "reason": "idle_or_locked", "app_name": app_name}

        path = Path(screenshot_path)
        if not path.exists():
            return {"ok": False, "skipped": False, "reason": "missing_screenshot"}

        self._last_run_at = now
        ocr_text, ocr_error = self._ocr_with_apple_vision(path)
        if not ocr_text:
            return {"ok": False, "skipped": False, "reason": "ocr_empty", "error": ocr_error}

        ocr_text = ocr_text[: self.max_ocr_chars]
        self._write_ocr_snapshot(path, ocr_text)
        extracted = self._extract_memories(ocr_text=ocr_text, app_name=app_name)
        if not extracted:
            return {"ok": False, "skipped": False, "reason": "llm_extract_empty", "app_name": app_name}

        timestamp = datetime.now().isoformat(timespec="seconds")
        activity = str(extracted.get("activity") or "").strip()
        saved = 0
        skipped_duplicates = 0
        for kind, values in (
            ("memory", extracted.get("memories") or []),
            ("task", extracted.get("tasks") or []),
        ):
            if not isinstance(values, list):
                continue
            for value in values:
                text = str(value).strip()
                if not text:
                    continue
                ok = self._save_if_new(
                    text=text,
                    metadata={
                        "kind": kind,
                        "app_name": app_name,
                        "activity": activity,
                        "source": source,
                        "screenshot_path": str(path),
                        "timestamp": timestamp,
                    },
                )
                if ok:
                    saved += 1
                else:
                    skipped_duplicates += 1

        if activity:
            self._append_jsonl(
                self.activity_jsonl,
                {
                    "id": str(uuid.uuid4()),
                    "timestamp": timestamp,
                    "app_name": app_name,
                    "activity": activity,
                    "source": source,
                    "screenshot_path": str(path),
                },
            )

        return {
            "ok": True,
            "saved": saved,
            "duplicates": skipped_duplicates,
            "activity": activity,
            "app_name": app_name,
        }

    def _ocr_with_apple_vision(self, image_path: Path) -> Tuple[str, str]:
        if sys.platform != "darwin":
            return "", "Apple Vision OCR is only available on macOS."
        if not self.vision_ocr_script.exists():
            return "", f"Missing OCR script: {self.vision_ocr_script}"
        try:
            proc = subprocess.run(
                ["swift", str(self.vision_ocr_script), str(image_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception as exc:
            return "", str(exc)
        if proc.returncode != 0:
            return "", (proc.stderr or proc.stdout or "Apple Vision OCR failed").strip()
        return (proc.stdout or "").strip(), ""

    def _extract_memories(self, ocr_text: str, app_name: str) -> Dict:
        prompt = (
            "You extract durable personal memory from OCR text. Return strict JSON only.\n"
            "Extract only facts that are useful later. Avoid passwords, secrets, API keys, OTPs, credit cards, "
            "private tokens, and highly sensitive data. Do not store transient UI noise.\n"
            "Schema: {\"memories\": [\"...\"], \"tasks\": [\"...\"], \"activity\": \"...\"}\n"
            f"App: {app_name or 'unknown'}\n"
            f"Screen text:\n{ocr_text}"
        )
        messages = [
            {"role": "system", "content": "Return only valid JSON for CALCIE screen memory extraction."},
            {"role": "user", "content": prompt},
        ]
        try:
            raw = self.llm_collect_text(messages, max_output_tokens=350, forced_provider=self.provider).strip()
        except TypeError:
            try:
                raw = self.llm_collect_text(messages, max_output_tokens=350).strip()
            except Exception:
                return {}
        except Exception:
            return {}
        parsed = self._extract_json_object(raw)
        if not parsed:
            return {}
        return {
            "memories": self._safe_string_list(parsed.get("memories")),
            "tasks": self._safe_string_list(parsed.get("tasks")),
            "activity": str(parsed.get("activity") or "").strip()[:500],
        }

    def _save_if_new(self, text: str, metadata: Dict[str, str]) -> bool:
        text = re.sub(r"\s+", " ", text).strip()
        if not text or self._looks_sensitive(text):
            return False

        collection = self._get_chroma_collection()
        if collection is not None:
            try:
                result = collection.query(query_texts=[text], n_results=1)
                distances = result.get("distances") or []
                nearest = distances[0][0] if distances and distances[0] else None
                if nearest is not None and float(nearest) <= self.dedup_threshold:
                    return False
                collection.add(documents=[text], metadatas=[metadata], ids=[str(uuid.uuid4())])
                return True
            except Exception as exc:
                self._chroma_error = str(exc)

        if self._jsonl_has_similar_memory(text):
            return False
        self._append_jsonl(
            self.memory_jsonl,
            {
                "id": str(uuid.uuid4()),
                "text": text,
                **metadata,
            },
        )
        return True

    def _get_chroma_collection(self):
        if self.store_backend == "jsonl":
            return None
        if self._chroma_collection is not None:
            return self._chroma_collection
        try:
            import chromadb  # type: ignore
        except Exception as exc:
            self._chroma_error = str(exc)
            return None
        try:
            client = chromadb.PersistentClient(path=str(self.memory_dir / "chroma"))
            self._chroma_collection = client.get_or_create_collection("screen_memory")
            return self._chroma_collection
        except Exception as exc:
            self._chroma_error = str(exc)
            return None

    def _jsonl_has_similar_memory(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        if not self.memory_jsonl.exists():
            return False
        try:
            lines = self.memory_jsonl.read_text(encoding="utf-8").splitlines()[-self.max_existing_docs :]
        except Exception:
            return False
        # Chroma distance threshold is not comparable to SequenceMatcher, so use a conservative fuzzy fallback.
        fuzzy_duplicate_ratio = max(0.82, 1.0 - self.dedup_threshold)
        for line in lines:
            try:
                item = json.loads(line)
            except Exception:
                continue
            existing = self._normalize_text(str(item.get("text") or ""))
            if not existing:
                continue
            if existing == normalized:
                return True
            if difflib.SequenceMatcher(None, existing, normalized).ratio() >= fuzzy_duplicate_ratio:
                return True
        return False

    def _frontmost_app_name(self) -> str:
        if sys.platform != "darwin":
            return ""
        try:
            proc = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to get name of first application process whose frontmost is true',
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
        except Exception:
            return ""
        if proc.returncode != 0:
            return ""
        return (proc.stdout or "").strip()

    def _should_skip_for_idle_or_lock(self, app_name: str) -> bool:
        if app_name.lower() in {"loginwindow", "screensaverengine"}:
            return True
        idle = self._mac_idle_seconds()
        return idle is not None and idle >= self.idle_skip_s

    def _mac_idle_seconds(self) -> Optional[float]:
        if sys.platform != "darwin":
            return None
        try:
            proc = subprocess.run(
                ["ioreg", "-c", "IOHIDSystem"],
                capture_output=True,
                text=True,
                timeout=2,
            )
        except Exception:
            return None
        match = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', proc.stdout or "")
        if not match:
            return None
        try:
            return int(match.group(1)) / 1_000_000_000.0
        except ValueError:
            return None

    def _write_ocr_snapshot(self, image_path: Path, text: str) -> None:
        try:
            name = image_path.with_suffix(".txt").name
            (self.ocr_dir / name).write_text(text, encoding="utf-8")
        except Exception:
            pass

    def _append_jsonl(self, path: Path, payload: Dict) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=True) + "\n")
        except Exception:
            pass

    def _extract_json_object(self, text: str) -> Optional[Dict]:
        if not text:
            return None
        candidate = text.strip()
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, flags=re.DOTALL | re.IGNORECASE)
        if fence:
            candidate = fence.group(1)
        else:
            match = re.search(r"(\{.*\})", candidate, flags=re.DOTALL)
            if match:
                candidate = match.group(1)
        try:
            parsed = json.loads(candidate)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _safe_string_list(self, value) -> List[str]:
        if not isinstance(value, list):
            return []
        out: List[str] = []
        for item in value:
            text = re.sub(r"\s+", " ", str(item)).strip()
            if text and not self._looks_sensitive(text):
                out.append(text[:500])
        return out[:8]

    def _looks_sensitive(self, text: str) -> bool:
        lowered = text.lower()
        sensitive_markers = {
            "password",
            "passcode",
            "otp",
            "api key",
            "secret key",
            "access token",
            "refresh token",
            "bearer ",
            "credit card",
            "cvv",
        }
        if any(marker in lowered for marker in sensitive_markers):
            return True
        if re.search(r"\b[A-Za-z0-9_\-]{32,}\b", text):
            return True
        return False

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.lower()).strip()

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

    def _env_float(self, name: str, default: float, min_value: float, max_value: float) -> float:
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            return default
        try:
            value = float(raw)
        except ValueError:
            return default
        return max(min_value, min(max_value, value))
