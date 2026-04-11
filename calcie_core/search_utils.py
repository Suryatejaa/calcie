"""Search and text cleanup helper utilities."""

import html
import re
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional


LOW_SIGNAL_MARKERS = [
    "visit bbc for trusted reporting",
    "view cnn world news today",
    "world news breaking news video headlines",
    "more of the latest stories",
    "bbc home breaking news world news",
    "home breaking news",
    "official website",
    "check who won today s ipl match",
    "match results of all ipl teams",
]


def truncate_text(text: str, max_chars: int = 180) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip(" ,;:") + "..."


def strip_html(text: str) -> str:
    clean = html.unescape(text or "")
    clean = clean.replace("<![CDATA[", " ").replace("]]>", " ")
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def parse_news_datetime(raw_date: str):
    if not raw_date:
        return None
    candidate = raw_date.strip()
    try:
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        dt = datetime.fromisoformat(candidate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def is_low_signal_result(title: str, body: str, normalize_text: Callable[[str], str]) -> bool:
    combined = normalize_text(f"{title} {body}")
    return any(marker in combined for marker in LOW_SIGNAL_MARKERS)


def format_news_results(
    results: Iterable[dict],
    is_low_signal: Callable[[str, str], bool],
    truncator: Callable[[str, int], str],
) -> str:
    lines = []
    for r in results:
        title = (r.get("title") or "").strip()
        body = (r.get("body") or "").strip()
        source = (r.get("source") or "").strip()
        if not title or len(title) < 8:
            continue
        if is_low_signal(title, body):
            continue

        short_body = truncator(body, 180)
        if source:
            lines.append(f"{title} ({source}): {short_body}")
        else:
            lines.append(f"{title}: {short_body}")
        if len(lines) >= 3:
            break

    return "\n\n".join(lines)


def is_live_sports_query(normalized_text: str) -> bool:
    if not normalized_text:
        return False

    sports_keywords = {
        "ipl", "tipl", "cricket", "match", "score", "scores", "winner", "won", "own",
        "result", "fixture", "fixtures", "points table", "standings", "vs",
        "rr", "mi", "csk", "rcb", "kkr", "gt", "srh", "dc", "pbks", "lsg",
    }
    temporal_keywords = {
        "last night", "yesterday", "today", "latest", "current", "recent",
        "tonight", "live", "now", "just now", "update",
    }

    has_sports = any(k in normalized_text for k in sports_keywords)
    has_temporal = any(k in normalized_text for k in temporal_keywords)
    asks_outcome = bool(re.search(r"\bwho\s+(won|own)\b", normalized_text))
    always_live_sports = any(k in normalized_text for k in ["points table", "standings", "fixtures", "fixture"])
    return (has_sports and has_temporal) or asks_outcome or always_live_sports


def extract_ipl_team_codes(normalized_text: str, ipl_team_aliases: dict) -> list:
    hits = []
    for code, aliases in ipl_team_aliases.items():
        for alias in aliases:
            match = re.search(rf"\b{re.escape(alias)}\b", normalized_text)
            if match:
                hits.append((match.start(), code))
                break

    hits.sort(key=lambda x: x[0])
    found = []
    for _, code in hits:
        if code not in found:
            found.append(code)
    return found


def team_code_from_fragment(
    fragment: str,
    normalize_text: Callable[[str], str],
    ipl_team_aliases: dict,
) -> Optional[str]:
    frag = normalize_text(fragment)
    best = None
    best_len = 0
    for code, aliases in ipl_team_aliases.items():
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias)}\b", frag):
                alias_len = len(alias)
                if alias_len > best_len:
                    best = code
                    best_len = alias_len
    return best


def extract_vs_team_pair(
    normalized_text: str,
    normalize_text: Callable[[str], str],
    ipl_team_aliases: dict,
) -> list:
    tokens = normalized_text.split()
    for i, token in enumerate(tokens):
        if token != "vs":
            continue
        left_fragment = " ".join(tokens[max(0, i - 4):i])
        right_fragment = " ".join(tokens[i + 1:i + 5])
        left_code = team_code_from_fragment(left_fragment, normalize_text, ipl_team_aliases)
        right_code = team_code_from_fragment(right_fragment, normalize_text, ipl_team_aliases)
        if left_code and right_code and left_code != right_code:
            return [left_code, right_code]
    return []


def normalize_search_query(
    raw_query: str,
    normalize_text: Callable[[str], str],
    ipl_team_aliases: dict,
) -> str:
    query = (raw_query or "").strip()
    if not query:
        return "latest world news today"

    normalized = normalize_text(query)
    if not normalized:
        return query

    cleanup_noise = [
        "for text or hey calcie",
        "for text or calcie",
        "type mode waiting for text",
        "waiting for text or hey calcie",
        "hey calcie",
    ]
    for noise in cleanup_noise:
        normalized = normalized.replace(noise, " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = re.sub(r"\bipl[a-z]+\b", "ipl", normalized)

    token_fixes = {
        "tipl": "ipl",
        "ipll": "ipl",
        "nigh": "night",
    }
    tokens = [token_fixes.get(t, t) for t in normalized.split()]
    normalized = " ".join(tokens).strip()
    if not normalized:
        return "latest world news today"

    if "news" in normalized or "headline" in normalized:
        stop_words = {
            "what", "is", "the", "latest", "today", "current", "recent",
            "trending", "news", "headline", "headlines", "for", "me",
            "show", "tell", "give", "please",
        }
        topic_words = [w for w in normalized.split() if w not in stop_words]
        if topic_words:
            topic = " ".join(topic_words[:5])
            return f"latest {topic} news today"
        return "latest world news today"

    teams = extract_vs_team_pair(normalized, normalize_text, ipl_team_aliases) or extract_ipl_team_codes(
        normalized, ipl_team_aliases
    )
    if len(teams) >= 2:
        matchup = f"{teams[0]} vs {teams[1]}"
        if any(t in normalized for t in ["last night", "yesterday", "today", "latest", "current", "recent"]):
            return f"{matchup} ipl match result last night winner margin"
        return f"{matchup} ipl match result"

    sports_terms = {"ipl", "cricket", "match", "score", "scores", "winner", "won", "own", "result"}
    if any(term in normalized for term in sports_terms):
        if "ipl" in normalized:
            if "points table" in normalized or "standings" in normalized:
                return "ipl points table latest"
            if "score" in normalized or "scores" in normalized:
                return "latest ipl score today"
            if any(t in normalized for t in ["last night", "yesterday", "today", "latest", "current", "recent"]):
                return "ipl yesterday match winner scorecard"
        if re.search(r"\bwho\s+(won|own)\b", normalized):
            if "result" in normalized:
                return normalized
            if "match" in normalized:
                return f"{normalized} result"
            return f"{normalized} match result"

    return normalized


def extract_direct_search_query(
    text: str,
    normalize_text: Callable[[str], str],
    normalize_search_query_fn: Callable[[str], str],
    is_live_sports_query_fn: Callable[[str], bool],
):
    raw = (text or "").strip()
    if not raw:
        return None

    explicit_patterns = [
        r"^\s*search\s*[,:\-]?\s*(.+)$",
        r"^\s*web\s*search\s*[,:\-]?\s*(.+)$",
        r"^\s*look\s*up\s*[,:\-]?\s*(.+)$",
        r"^\s*find\s*[,:\-]?\s*(.+)$",
    ]
    for pattern in explicit_patterns:
        match = re.match(pattern, raw, flags=re.IGNORECASE)
        if match:
            query = match.group(1).strip()
            if not query:
                return None
            return normalize_search_query_fn(query)

    normalized = normalize_text(raw)
    if not normalized:
        return None

    if normalized in {"news", "latest news", "today news", "headlines"}:
        return "latest world news today"

    live_markers = {"latest", "today", "current", "recent", "trending", "headlines", "news"}
    if any(marker in normalized for marker in live_markers):
        return normalize_search_query_fn(raw)

    if is_live_sports_query_fn(normalized):
        return normalize_search_query_fn(raw)
    return None


def refine_sports_query(
    user_input: str,
    direct_query: str,
    normalize_text: Callable[[str], str],
    ipl_team_aliases: dict,
) -> str:
    normalized = normalize_text(f"{user_input} {direct_query}")
    teams = extract_vs_team_pair(normalized, normalize_text, ipl_team_aliases) or extract_ipl_team_codes(
        normalized, ipl_team_aliases
    )
    if len(teams) >= 2:
        matchup = f"{teams[0]} vs {teams[1]}"
        return f"{matchup} ipl match result winner margin top scorer top wicket taker"
    if "ipl" in normalized or "tipl" in normalized:
        if any(k in normalized for k in ["last night", "night", "yesterday", "who won", "who own"]):
            return "ipl yesterday match winner margin top scorer top wicket taker"
        if any(k in normalized for k in ["score", "scores", "result", "winner"]):
            return "latest ipl match result winner margin top scorer"
        if any(k in normalized for k in ["points table", "standings"]):
            return "latest ipl points table standings"
    return direct_query


def sports_answer_mentions_teams(
    answer_text: str,
    team_codes: list,
    normalize_text: Callable[[str], str],
    ipl_team_aliases: dict,
) -> bool:
    normalized_answer = normalize_text(answer_text)
    if not normalized_answer or not team_codes:
        return False
    checks = team_codes[:2]
    for code in checks:
        aliases = ipl_team_aliases.get(code, [code])
        if not any(re.search(rf"\b{re.escape(alias)}\b", normalized_answer) for alias in aliases):
            return False
    return True


def is_news_request(text: str, normalize_text: Callable[[str], str]) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    if normalized in {"news", "latest news", "today news", "headlines"}:
        return True
    if "news" in normalized and any(k in normalized for k in ["latest", "today", "headline", "current"]):
        return True
    return False
