"""Command routing, arbitration, and fuzzy dispatch helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple


@dataclass
class RouteDecision:
    route: Optional[str]
    confidence: float
    reason: str
    rewritten_input: str


class CommandArbiter:
    """Lightweight orchestrator for skill routing with typo tolerance."""

    ROUTES = ("coding", "vision", "agentic", "app", "computer", "search")

    _COMMAND_ALIASES = {
        "search": {"search", "serch", "seach", "sreach", "lookup", "look", "find"},
        "code": {"code", "cod", "coed", "kode"},
        "control": {"control", "controll", "cntrl", "computer"},
        "open": {"open", "opne", "oen", "launch", "start"},
        "play": {"play", "plya", "plai", "resume", "continue"},
        "order": {"order", "oder", "ordr", "buy", "checkout", "book"},
        "vision": {"vision", "monitor", "moniter", "watch", "observe", "screen"},
    }

    _COMMAND_ROUTE = {
        "search": "search",
        "code": "coding",
        "control": "computer",
        "open": "app",
        "play": "app",
        "order": "agentic",
        "vision": "vision",
    }

    _ROUTE_KEYWORDS = {
        "coding": {
            "code", "debug", "bug", "fix", "implement", "refactor",
            "file", "function", "class", "repo", "readme", "script",
            "python", "javascript", "java", "typescript",
        },
        "agentic": {
            "order", "buy", "checkout", "book", "payment", "cart", "amazon",
            "flipkart", "netflix", "prime", "ticket", "reservation",
        },
        "vision": {
            "vision", "monitor", "watch", "observe", "screen", "screenshot",
            "dashboard", "alert", "warning", "terminal", "loop",
        },
        "app": {
            "open", "launch", "start", "play", "resume", "continue",
            "chrome", "safari", "spotify", "youtube", "yt", "ytmusic",
            "whatsapp", "instagram", "insta", "discord", "slack",
        },
        "computer": {
            "control", "computer", "click", "double", "right", "scroll",
            "type", "press", "hotkey", "screenshot", "cursor", "mouse",
            "screen", "move",
        },
        "search": {
            "search", "lookup", "find", "latest", "news", "score",
            "result", "ipl", "points", "table", "headlines",
            "today", "yesterday", "current", "web", "online",
        },
    }

    def __init__(
        self,
        threshold: float = 0.62,
        ambiguous_delta: float = 0.08,
        leading_correction_threshold: float = 0.76,
    ):
        self.threshold = max(0.35, min(0.95, float(threshold)))
        self.ambiguous_delta = max(0.02, min(0.2, float(ambiguous_delta)))
        self.leading_correction_threshold = max(0.68, min(0.95, float(leading_correction_threshold)))

    def decide(self, user_input: str, strict_flags: Optional[Dict[str, bool]] = None) -> RouteDecision:
        raw = (user_input or "").strip()
        if not raw:
            return RouteDecision(route=None, confidence=0.0, reason="empty_input", rewritten_input=raw)

        strict_flags = strict_flags or {}
        normalized = self._normalize(raw)
        tokens = normalized.split()

        rewritten, rewritten_route, rewritten_score = self._rewrite_leading_verb(raw)
        rewritten_norm = self._normalize(rewritten)
        rewritten_tokens = rewritten_norm.split()

        route_scores: Dict[str, float] = {}
        route_reasons: Dict[str, str] = {}
        for route in self.ROUTES:
            strict = bool(strict_flags.get(route))
            keyword_score, keyword_hits = self._keyword_score(rewritten_tokens, self._ROUTE_KEYWORDS[route])
            score = 1.0 if strict else keyword_score

            if rewritten_route == route:
                score += 0.35 * rewritten_score
            score += self._leading_route_bonus(route, rewritten_norm)
            score = max(0.0, min(1.0, score))

            reason_bits: List[str] = []
            if strict:
                reason_bits.append("strict")
            if rewritten_route == route and rewritten != raw:
                reason_bits.append(f"typo_fix:{rewritten.split(' ', 1)[0]}")
            if keyword_hits:
                reason_bits.append("kw:" + ",".join(keyword_hits[:3]))
            if not reason_bits:
                reason_bits.append("weak_signal")

            route_scores[route] = score
            route_reasons[route] = "|".join(reason_bits)

        ranked = sorted(route_scores.items(), key=lambda kv: kv[1], reverse=True)
        top_route, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0

        if top_score < self.threshold:
            return RouteDecision(
                route=None,
                confidence=round(top_score, 3),
                reason=f"below_threshold:{top_route}:{route_reasons[top_route]}",
                rewritten_input=rewritten,
            )

        top_strict = bool(strict_flags.get(top_route))
        if not top_strict and (top_score - second_score) < self.ambiguous_delta and top_score < 0.9:
            return RouteDecision(
                route=None,
                confidence=round(top_score, 3),
                reason=f"ambiguous:{top_route}:{route_reasons[top_route]}",
                rewritten_input=rewritten,
            )

        return RouteDecision(
            route=top_route,
            confidence=round(top_score, 3),
            reason=route_reasons[top_route],
            rewritten_input=rewritten,
        )

    def _normalize(self, text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())).strip()

    def _keyword_score(self, tokens: List[str], keywords: set) -> Tuple[float, List[str]]:
        if not tokens:
            return 0.0, []
        hits: List[str] = []
        score = 0.0
        for kw in keywords:
            if kw in tokens:
                hits.append(kw)
                score += 0.14
                continue
            for token in tokens:
                if len(token) < 3:
                    continue
                if SequenceMatcher(None, token, kw).ratio() >= 0.86:
                    hits.append(f"{token}->{kw}")
                    score += 0.06
                    break
        return min(0.6, score), hits

    def _leading_route_bonus(self, route: str, normalized_text: str) -> float:
        if not normalized_text:
            return 0.0
        checks = {
            "coding": ("code ",),
            "vision": ("vision ", "monitor ", "watch my screen ", "monitor my screen ", "analyze my screen "),
            "agentic": ("order ", "buy ", "checkout ", "book "),
            "app": ("open ", "launch ", "start ", "play ", "resume ", "continue "),
            "computer": ("control ", "computer ", "click ", "scroll ", "type ", "press ", "hotkey ", "screenshot "),
            "search": ("search ", "lookup ", "find "),
        }
        return 0.22 if normalized_text.startswith(checks[route]) else 0.0

    def _rewrite_leading_verb(self, raw: str) -> Tuple[str, Optional[str], float]:
        parts = (raw or "").strip().split(None, 1)
        if not parts:
            return raw, None, 0.0
        head = re.sub(r"[^a-z0-9]", "", parts[0].lower())
        if len(head) < 3:
            return raw, None, 0.0

        best_canonical = None
        best_route = None
        best_score = 0.0

        for canonical, aliases in self._COMMAND_ALIASES.items():
            for alias in aliases:
                score = SequenceMatcher(None, head, alias).ratio()
                if score > best_score:
                    best_score = score
                    best_canonical = canonical
                    best_route = self._COMMAND_ROUTE.get(canonical)

        if not best_canonical or best_score < self.leading_correction_threshold:
            return raw, None, 0.0

        if head == best_canonical:
            return raw, best_route, best_score

        tail = parts[1] if len(parts) > 1 else ""
        rewritten = f"{best_canonical} {tail}".strip()
        return rewritten, best_route, best_score


class LocalCommandInterpreter:
    """Rewrite natural phrasing into CALCIE-native commands without using an LLM."""

    def rewrite(self, user_input: str) -> str:
        raw = (user_input or "").strip()
        if not raw:
            return raw

        normalized = self._normalize(raw)
        if not normalized:
            return raw

        explicit_prefixes = (
            "vision ",
            "monitor ",
            "screen monitor ",
            "screen vision ",
            "control ",
            "computer ",
            "open ",
            "launch ",
            "start ",
            "play ",
            "search ",
            "code ",
            "order ",
            "buy ",
        )
        if normalized.startswith(explicit_prefixes):
            return raw

        rewritten = (
            self._rewrite_vision_command(raw, normalized)
            or self._rewrite_control_command(raw, normalized)
        )
        return rewritten or raw

    def _normalize(self, text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())).strip()

    def _rewrite_vision_command(self, raw: str, normalized: str) -> Optional[str]:
        if re.search(r"\b(stop|end|disable)\b", normalized) and re.search(
            r"\b(vision|monitor|watching|screen monitoring|screen watch)\b", normalized
        ):
            return "vision stop"

        monitor_match = re.search(
            r"\b(?:watch|monitor|keep watching|keep an eye on)\s+(?:my\s+)?screen\s+for\s+(.+)$",
            normalized,
        )
        if monitor_match:
            goal = monitor_match.group(1).strip()
            if goal:
                return f"vision start {goal}"

        if "screen" not in normalized:
            return None

        once_markers = (
            "check", "look", "see", "detect", "inspect", "analyze",
            "tell me if", "is there", "does this", "whether", "find",
        )
        if any(marker in normalized for marker in once_markers):
            return f"vision once {raw}"
        return None

    def _rewrite_control_command(self, raw: str, normalized: str) -> Optional[str]:
        screenshot_markers = {
            "take screenshot",
            "capture screenshot",
            "take a screenshot",
            "capture the screen",
        }
        if any(marker in normalized for marker in screenshot_markers):
            return "screenshot"

        if "scroll" in normalized:
            direction = "down"
            if re.search(r"\bup\b", normalized):
                direction = "up"
            amount = 600
            if re.search(r"\b(a bit|little|slightly)\b", normalized):
                amount = 300
            elif re.search(r"\bmore\b", normalized):
                amount = 900
            explicit_amount = re.search(r"\b(\d{2,4})\b", normalized)
            if explicit_amount:
                amount = int(explicit_amount.group(1))
            return f"control scroll {direction} {amount}"

        type_match = re.match(r"^(?:enter|type|write)\s+(.+)$", raw.strip(), flags=re.IGNORECASE)
        if type_match:
            text = type_match.group(1).strip()
            if text:
                return f"control type {text}"
        return None
