"""HTTP sync client for CALCIE V1 cloud/mobile interoperability."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional


class CalcieSyncClient:
    def __init__(self, base_url: str, user_id: str, device_id: str, device_type: str, timeout_s: int = 12):
        self.base_url = (base_url or "").rstrip("/")
        self.user_id = user_id
        self.device_id = device_id
        self.device_type = device_type
        self.timeout_s = max(4, int(timeout_s))

    def _request(self, method: str, path: str, payload: Optional[dict] = None):
        if not self.base_url:
            raise RuntimeError("Sync base URL is empty")
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Content-Type": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        with urllib.request.urlopen(req, timeout=self.timeout_s) as res:
            body = res.read().decode("utf-8", errors="replace")
            if not body.strip():
                return {}
            return json.loads(body)

    def register_device(self, label: str = "", metadata: Optional[dict] = None) -> bool:
        try:
            self._request(
                "POST",
                "/devices/register",
                {
                    "user_id": self.user_id,
                    "device_id": self.device_id,
                    "device_type": self.device_type,
                    "label": label or self.device_id,
                    "metadata": metadata or {},
                },
            )
            return True
        except Exception:
            return False

    def add_message(self, role: str, content: str) -> bool:
        try:
            self._request(
                "POST",
                "/messages",
                {
                    "user_id": self.user_id,
                    "device_id": self.device_id,
                    "role": role,
                    "content": content,
                },
            )
            return True
        except Exception:
            return False

    def list_messages(self, limit: int = 40, after_id: int = 0) -> List[Dict]:
        try:
            query = urllib.parse.urlencode(
                {
                    "user_id": self.user_id,
                    "limit": max(1, min(500, int(limit))),
                    "after_id": max(0, int(after_id)),
                }
            )
            data = self._request("GET", f"/messages?{query}")
            rows = data.get("messages") or []
            if isinstance(rows, list):
                return rows
        except Exception:
            pass
        return []

    def get_facts(self) -> List[str]:
        try:
            data = self._request("GET", f"/facts/{urllib.parse.quote(self.user_id)}")
            facts = data.get("facts") or []
            if isinstance(facts, list):
                return [str(x) for x in facts]
        except Exception:
            pass
        return []

    def set_facts(self, facts: List[str]) -> bool:
        try:
            self._request(
                "PUT",
                f"/facts/{urllib.parse.quote(self.user_id)}",
                {"facts": [str(x) for x in (facts or [])]},
            )
            return True
        except Exception:
            return False

    def send_command(self, target_device: str, content: str, requires_confirm: bool = False) -> bool:
        try:
            self._request(
                "POST",
                "/commands",
                {
                    "user_id": self.user_id,
                    "from_device": self.device_id,
                    "target_device": target_device,
                    "content": content,
                    "requires_confirm": bool(requires_confirm),
                },
            )
            return True
        except Exception:
            return False

    def poll_commands(self, limit: int = 20) -> List[Dict]:
        try:
            query = urllib.parse.urlencode(
                {
                    "user_id": self.user_id,
                    "device_id": self.device_id,
                    "limit": max(1, min(100, int(limit))),
                }
            )
            data = self._request("GET", f"/commands/poll?{query}")
            rows = data.get("commands") or []
            if isinstance(rows, list):
                return rows
        except Exception:
            pass
        return []

    def ack_command(self, command_id: int, status: str, result: str = "") -> bool:
        try:
            self._request(
                "POST",
                f"/commands/{int(command_id)}/ack",
                {"status": status, "result": result[:1000]},
            )
            return True
        except Exception:
            return False

