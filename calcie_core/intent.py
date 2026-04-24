"""Intent and activation helper utilities."""

import re
from difflib import SequenceMatcher
from typing import Dict, Iterable, Optional, Tuple


def classify_input(text: str) -> str:
    """Lightweight input classifier for response-style control."""
    if not text:
        return "DEFAULT"

    lowered = text.lower().strip()
    normalized = re.sub(r"[^a-z0-9\s']", " ", lowered)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    collapsed = normalized.replace(" ", "").replace("'", "")
    token_count = len(normalized.split())

    greetings = {"hi", "hello", "hey", "yo", "good morning", "good evening"}
    small_talk = {
        "whats up", "what's up", "sup", "wassup", "wazzup",
        "how are you", "how r u", "hows it going", "how's it going",
        "good afternoon",
    }
    compact_small_talk = {"whatsup", "wassup", "wazzup", "sup", "yo"}
    query_keywords = {"help", "build", "fix", "explain", "implement", "debug", "error"}

    repeated_small_talk = any(
        re.fullmatch(rf"(?:{re.escape(phrase)}){{2,}}", collapsed) is not None
        for phrase in compact_small_talk
    )
    if normalized in greetings or normalized in small_talk or collapsed in compact_small_talk or repeated_small_talk:
        return "GREETING"

    if "?" in lowered:
        return "QUERY"

    starts_like_question = bool(re.match(r"^(how|why|what|when|where|which|who)\b", normalized))
    if token_count >= 3 and (starts_like_question or any(q in normalized for q in query_keywords)):
        return "QUERY"

    return "DEFAULT"


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())).strip()


def contains_name(text: str, wake_words: Iterable[str]) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False

    if any(re.search(rf"\b{re.escape(w)}\b", normalized) for w in wake_words):
        return True

    tokens = normalized.split()
    candidates = tokens + [f"{tokens[i]} {tokens[i + 1]}" for i in range(len(tokens) - 1)]
    for candidate in candidates:
        for wake in wake_words:
            if SequenceMatcher(None, candidate, wake).ratio() >= 0.84:
                return True
    return False


def similarity_score(text: str, hook_phrases: Iterable[str]) -> float:
    normalized = normalize_text(text)
    if not normalized:
        return 0.0

    best = 0.0
    for phrase in hook_phrases:
        phrase_norm = normalize_text(phrase)
        if not phrase_norm:
            continue
        if phrase_norm in normalized:
            return 1.0
        score = SequenceMatcher(None, normalized, phrase_norm).ratio()
        if score > best:
            best = score
    return best


def detect_intent(text: str, intent_triggers: Dict[str, Iterable[str]]) -> Optional[str]:
    normalized = normalize_text(text)
    if not normalized:
        return None

    intent_scores = {}
    for intent, keywords in intent_triggers.items():
        intent_scores[intent] = sum(1 for k in keywords if k in normalized)

    max_score = max(intent_scores.values())
    if max_score == 0:
        return None

    # Prefer high-urgency intent on ties.
    priority = {"confusion": 3, "decision": 2, "help": 1}
    candidates = [intent for intent, score in intent_scores.items() if score == max_score]
    return max(candidates, key=lambda i: priority.get(i, 0))


def activation_signal(
    text: str,
    wake_words: Iterable[str],
    hook_phrases: Iterable[str],
    intent_triggers: Dict[str, Iterable[str]],
    hook_similarity_threshold: float,
) -> Tuple[bool, str, float, Optional[str]]:
    name_detected = contains_name(text, wake_words)
    similarity = similarity_score(text, hook_phrases)
    intent = detect_intent(text, intent_triggers)

    if name_detected:
        return True, "name", similarity, intent
    if similarity >= hook_similarity_threshold:
        return True, f"hook:{similarity:.2f}", similarity, intent
    if intent in {"help", "decision", "confusion"}:
        return True, f"intent:{intent}", similarity, intent
    return False, "none", similarity, intent


def limit_words(text: str, max_words: int) -> str:
    words = (text or "").split()
    if len(words) <= max_words:
        return (text or "").strip()
    trimmed = " ".join(words[:max_words]).rstrip(" ,;:")
    return f"{trimmed}."


def is_profile_query(normalized_text: str) -> bool:
    if not normalized_text:
        return False
    patterns = [
        r"\bsay my name\b",
        r"\bwhat(?:s| is)? my name\b",
        r"\bmy name\b",
        r"\btell me about myself\b",
        r"\btell me about my self\b",
        r"\babout me\b",
        r"\bwho am i\b",
        r"\bwhat do you know about me\b",
        r"\bwho is this\b",
        r"\bwho am i to you\b",
    ]
    return any(re.search(p, normalized_text) for p in patterns)


def needs_detailed_answer(normalized_text: str) -> bool:
    if not normalized_text:
        return False
    if is_profile_query(normalized_text):
        return False
    if len(normalized_text.split()) <= 6:
        return False
    detailed_markers = [
        "how", "why", "build", "implement", "debug", "fix", "explain",
        "architecture", "design", "roadmap", "plan", "strategy", "step by step",
    ]
    return any(marker in normalized_text for marker in detailed_markers)


def response_token_budget(
    normalized_text: str,
    input_type: str,
    use_web_grounding: bool,
    is_profile_query_flag: bool,
    quick_max_output_tokens: int,
    default_max_output_tokens: int,
) -> int:
    if input_type == "GREETING":
        return 80
    if is_profile_query_flag:
        return 220
    if use_web_grounding:
        return quick_max_output_tokens
    if len((normalized_text or "").split()) <= 7:
        return quick_max_output_tokens
    return default_max_output_tokens
