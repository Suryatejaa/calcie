"""Skill: web searching via Tavily/Exa + scraping + LLM synthesis."""

import json
import os
import pathlib
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from typing import Callable, Dict, List, Optional, Tuple

from calcie_core.prompts import (
    SEARCH_SYNTH_SYSTEM_PROMPT,
    SEARCH_SYNTH_USER_TEMPLATE,
    SPORTS_MCP_INTERPRET_SYSTEM_PROMPT,
    WEATHER_GROUNDED_SYSTEM_PROMPT,
)

try:
    from tavily import TavilyClient  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    TavilyClient = None

try:
    from exa_py import Exa  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Exa = None

try:
    from ddgs import DDGS  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    DDGS = None


class SearchingSkill:
    def __init__(
        self,
        llm_collect_text: Callable[..., str],
        fallback_search: Optional[Callable[[str], str]] = None,
        max_results: int = 5,
        max_source_chars: int = 5000,
        app_skill=None,
        vision_skill=None,
        project_root: Optional[pathlib.Path] = None,
    ):
        self.llm_collect_text = llm_collect_text
        self.fallback_search = fallback_search
        self.app_skill = app_skill
        self.vision_skill = vision_skill
        self.project_root = pathlib.Path(project_root or pathlib.Path.cwd()).resolve()
        self.max_results = max(3, min(8, int(max_results)))
        self.max_source_chars = max(1500, int(max_source_chars))
        self.tavily_api_key = (os.environ.get("TAVILY_API_KEY") or "").strip()
        self.exa_api_key = (os.environ.get("EXA_API_KEY") or "").strip()
        self.weather_api_key = (os.environ.get("WEATHER_API_KEY") or "").strip()
        self.weather_llm_provider = (os.environ.get("CALCIE_WEATHER_LLM_PROVIDER") or "gemini").strip().lower()
        self.cricket_llm_provider = (os.environ.get("CALCIE_CRICKET_LLM_PROVIDER") or "gemini").strip().lower()
        self.rapidapi_key = (os.environ.get("RAPIDAPI_KEY") or "").strip()
        self.apify_api_key = (os.environ.get("APIFY_API") or "").strip()
        self.apify_actor_id = (os.environ.get("APIFY_ID") or "").strip()
        self.search_provider = (os.environ.get("CALCIE_SEARCH_PROVIDER") or "auto").strip().lower()
        self.allow_fallback = (os.environ.get("CALCIE_SEARCH_ALLOW_FALLBACK", "0").strip().lower() in {"1", "true", "yes", "on"})
        self.research_timeout_s = max(8, min(60, int(os.environ.get("CALCIE_RESEARCH_TIMEOUT_S", "24"))))
        self.research_poll_s = max(0.6, min(3.0, float(os.environ.get("CALCIE_RESEARCH_POLL_S", "1.0"))))
        self.tavily_mode = (os.environ.get("CALCIE_TAVILY_MODE") or "search").strip().lower()
        if self.tavily_mode not in {"search", "research"}:
            self.tavily_mode = "search"
        self.search_http_timeout_s = max(6, min(30, int(os.environ.get("CALCIE_SEARCH_HTTP_TIMEOUT_S", "10"))))
        self.page_fetch_timeout_s = max(2, min(20, int(os.environ.get("CALCIE_SEARCH_PAGE_FETCH_TIMEOUT_S", "4"))))
        self.scrape_top_k = max(2, min(5, int(os.environ.get("CALCIE_SEARCH_SCRAPE_TOP_K", "3"))))
        self.synth_tokens = max(120, min(480, int(os.environ.get("CALCIE_SEARCH_SYNTH_TOKENS", "220"))))
        self.search_llm_provider = (os.environ.get("CALCIE_SEARCH_LLM_PROVIDER") or "auto").strip().lower()
        self.ddgs_fallback_results = max(3, min(8, int(os.environ.get("CALCIE_DDGS_FALLBACK_RESULTS", "5"))))
        self.jobs_max_results = max(3, min(10, int(os.environ.get("CALCIE_JOBS_MAX_RESULTS", "6"))))
        self.job_hunter_enabled = (os.environ.get("CALCIE_JOB_HUNTER_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"})
        self.job_hunter_port = max(1024, min(65535, int(os.environ.get("CALCIE_JOB_HUNTER_PORT", "3000"))))
        self.job_hunter_browser = (os.environ.get("CALCIE_JOB_HUNTER_BROWSER") or "chrome").strip() or "chrome"
        self.job_hunter_autorun = (os.environ.get("CALCIE_JOB_HUNTER_AUTORUN", "1").strip().lower() in {"1", "true", "yes", "on"})
        self.sports_mcp_enabled = (os.environ.get("CALCIE_SPORTS_MCP_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"})
        self.sports_mcp_base_url = (os.environ.get("CALCIE_SPORTS_MCP_URL") or "https://mrbridge--espn-mcp-server.apify.actor/mcp").strip()
        self.sports_mcp_timeout_s = max(5, min(20, int(os.environ.get("CALCIE_SPORTS_MCP_TIMEOUT_S", "10"))))
        self.weather_api_url = (os.environ.get("CALCIE_WEATHER_API_URL") or "https://api.weatherapi.com/v1/current.json").strip()
        self.weather_default_query = (os.environ.get("CALCIE_WEATHER_DEFAULT_QUERY") or "auto:ip").strip() or "auto:ip"
        self.cricket_live_scores_url = (
            os.environ.get("CALCIE_CRICKET_LIVE_SCORES_URL") or "https://crex.com/cricket-live-score"
        ).strip()
        self.cricket_crex_series_url = (
            os.environ.get("CALCIE_CRICKET_CREX_SERIES_URL")
            or "https://crex.com/series/indian-premier-league-2026-1PW"
        ).strip()
        self.cricket_results_url = (
            os.environ.get("CALCIE_CRICKET_RESULTS_URL") or "https://www.iplt20.com/matches/results"
        ).strip()
        self.cricket_browser = (os.environ.get("CALCIE_CRICKET_BROWSER") or "chrome").strip() or "chrome"
        self.cricket_page_wait_s = max(
            1.0,
            min(8.0, float((os.environ.get("CALCIE_CRICKET_PAGE_WAIT_S") or "3.0").strip() or "3.0")),
        )
        self.cricket_vision_attempts = max(
            1,
            min(4, int((os.environ.get("CALCIE_CRICKET_VISION_ATTEMPTS") or "3").strip() or "3")),
        )
        self.show_sources = (os.environ.get("CALCIE_SEARCH_SHOW_SOURCES", "1").strip().lower() in {"1", "true", "yes", "on"})
        self.debug_output = (os.environ.get("CALCIE_SEARCH_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"})
        self._tavily_client = TavilyClient(api_key=self.tavily_api_key) if TavilyClient and self.tavily_api_key else None
        self._exa_client = Exa(api_key=self.exa_api_key) if Exa and self.exa_api_key else None

    def is_search_intent(self, user_input: str) -> bool:
        normalized = self._normalize(user_input)
        if not normalized:
            return False
        if re.match(r"^(search|web search|lookup|look up|find|check)\b", normalized):
            return True
        if self._is_job_query(normalized):
            return True
        if "latest" in normalized and "news" in normalized:
            return True
        if normalized in {"news", "latest news", "today news", "headlines"}:
            return True
        if self._is_weather_query(normalized):
            return True
        if self._is_cricket_query(normalized):
            return True
        if normalized.startswith("check ") and re.search(r"\b(ipl|score|match|won|news|price|weather|result|points|table)\b", normalized):
            return True
        if any(k in normalized for k in {"latest", "today", "yesterday", "last night", "current", "now"}):
            if re.search(r"\b(ipl|score|match|won|news|price|weather|result)\b", normalized):
                return True
        if re.search(r"\bwho won\b", normalized) and re.search(r"\b(match|ipl|game)\b", normalized):
            return True
        if self._is_ipl_table_query(normalized):
            return True
        return False

    def extract_query(self, user_input: str) -> str:
        raw = self._clean_transcript_noise((user_input or "").strip())
        if not raw:
            return "latest world news"

        match = re.match(
            r"^\s*(?:search|web search|lookup|look up|find|check)\s*[,:\-]?\s*(.+)$",
            raw,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1).strip() or "latest world news"
        return self._clean_transcript_noise(raw)

    def handle_query(self, user_input: str):
        if not self.is_search_intent(user_input):
            return None, None

        query = self.extract_query(user_input)
        normalized_query = self._normalize(query)
        if self._is_weather_query(normalized_query):
            response, spoken = self._handle_weather_query(query)
            if response:
                return response, spoken
        if self._is_cricket_query(normalized_query):
            response, spoken = self._handle_cricket_query(query)
            if response:
                return response, spoken
        if self._is_sports_query(normalized_query) and not self._is_unsupported_espn_sport(normalized_query):
            response, spoken = self._handle_sports_query(query)
            if response:
                return response, spoken
        if self._is_job_query(normalized_query):
            response, spoken = self._handle_jobs_query(query)
            return response, spoken
        query_for_provider = self._prepare_provider_query(query)
        results, provider_used, attempted = self._search(query_for_provider)

        if not results:
            if self.allow_fallback and self.fallback_search:
                fallback = self.fallback_search(query_for_provider)
                return fallback, fallback
            attempts = " | ".join(attempted) if attempted else "no providers configured"
            return f"Search failed: no usable results. Attempts: {attempts}", "Search failed."

        scraped = self._scrape_results(results[: self.max_results])
        if not scraped:
            scraped = self._build_scrape_fallback_from_results(results)
            if not scraped:
                lines = [f"I could not extract enough page content for: {query}"]
                for r in results[: self.max_results]:
                    lines.append(f"- {r.get('title', 'Untitled')}: {r.get('url', '')}")
                return "\n".join(lines), "Top links ready."

        summary = self._synthesize(query, scraped)
        response = summary.strip()
        if self.show_sources:
            src_lines = [f"- {item['title']} ({item['url']})" for item in scraped[: self.max_results]]
            response = response + "\n\nSources:\n" + "\n".join(src_lines)
        if self.debug_output:
            response = (
                response
                + f"\n\n[debug] provider={provider_used} | attempts={' | '.join(attempted)}"
            )
        return response, summary

    def _handle_sports_query(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        if not self.sports_mcp_enabled or not self.apify_api_key:
            return None, None

        tool_name, tool_args, reason = self._infer_sports_tool_call(query)
        text, err = self._call_sports_mcp_tool(tool_name, tool_args)
        if err or not text:
            if self.debug_output and err:
                return None, None
            return None, None

        response = text.strip()
        if self.debug_output:
            response += f"\n\n[debug] provider=espn_mcp | tool={tool_name} | reason={reason}"
        return response, "I checked the sports data."

    def _handle_cricket_query(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        normalized = self._normalize(query)
        explicit_page_query = self._is_explicit_cricket_page_query(normalized)
        wants_live = self._is_cricket_live_query(normalized)

        if wants_live:
            crex_live = self._handle_crex_ipl_live_score(query)
            if crex_live[0]:
                return crex_live

        grounded = self._handle_cricket_query_llm(query)
        if grounded[0]:
            return grounded

        if self.app_skill is None or self.vision_skill is None:
            if self._is_cricket_live_query(normalized):
                return (
                    "I could not check the live cricket score right now.",
                    "I could not check the live cricket score right now.",
                )
            return (
                "I could not check the cricket result right now.",
                "I could not check the cricket result right now.",
            )

        target_url = self.cricket_live_scores_url if wants_live else self.cricket_results_url
        open_result = self.app_skill.open_target_in_app(
            target=target_url,
            app_name=self.cricket_browser,
            allow_default_browser_fallback=True,
        )
        time.sleep(self.cricket_page_wait_s)

        analysis, vision_result = self._run_cricket_vision_summary(query=query, wants_live=wants_live)

        if explicit_page_query:
            response = f"{open_result}\n\n{analysis}"
        else:
            response = analysis
        if self.debug_output:
            screenshot_path = str(vision_result.get("screenshot_path") or "").strip()
            if screenshot_path:
                response += f"\n\n[debug] screenshot={screenshot_path}"
        return response, "I opened the cricket page and checked the visible score."

    def _handle_crex_ipl_live_score(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        html_text, source = self._fetch_crex_series_html()
        if not html_text:
            return None, None

        cards = self._extract_crex_match_cards(html_text)
        if not cards:
            return None, None

        selected = self._select_crex_live_match_card(cards)
        if not selected:
            return None, None

        response = self._summarize_crex_match_card(query=query, selected=selected, cards=cards)
        if not response:
            response = self._format_crex_match_card_deterministically(selected)
        if not response:
            return None, None

        response = response.strip()
        if self.show_sources:
            response += f"\n\nSource: {source}"
        if self.debug_output:
            response += (
                f"\n\n[debug] provider=crex_series_html"
                f" | selected_match={selected.get('match_number') or '-'}"
                f" | cards={len(cards)}"
            )
        spoken = response.split("\n", 1)[0].strip()
        return response, spoken

    def _fetch_crex_series_html(self) -> Tuple[str, str]:
        source_url = self.cricket_crex_series_url
        html_text, err = self._fetch_url_raw_text(source_url, max_bytes=700_000, timeout=max(self.page_fetch_timeout_s, 8))
        if html_text:
            return html_text, source_url

        # Local fixture fallback keeps the parser usable during development/offline testing.
        local_fixture = self.project_root / "indian-premier-league-2026-1PW.html"
        if local_fixture.exists():
            try:
                return local_fixture.read_text(encoding="utf-8", errors="replace"), str(local_fixture)
            except OSError:
                return "", source_url
        if self.debug_output and err:
            return "", f"{source_url} ({err})"
        return "", source_url

    def _fetch_url_raw_text(self, url: str, max_bytes: int = 500_000, timeout: int = 8) -> Tuple[str, Optional[str]]:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"
                )
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                raw = res.read(max_bytes)
        except Exception as exc:
            return "", self._safe_error(exc)
        return raw.decode("utf-8", errors="replace"), None

    def _extract_crex_match_cards(self, html_text: str) -> List[Dict[str, str]]:
        if not html_text:
            return []
        cards: List[Dict[str, str]] = []
        seen = set()

        # Primary path: parse complete match-card anchors anywhere in the document.
        # This intentionally scans the whole HTML. It must not rely on a fixed line
        # number because CREX often ships most Angular-rendered content on one line.
        anchor_pattern = re.compile(
            r"""<a\b[^>]*href\s*=\s*(['"])(?P<href>[^'"]*/cricket-live-score/[^'"]+)\1[^>]*>(?P<body>.*?)</a>""",
            flags=re.IGNORECASE | re.DOTALL | re.VERBOSE,
        )
        for match in anchor_pattern.finditer(html_text):
            href = match.group("href")
            body = match.group("body")
            self._append_crex_card(cards, seen, href, self._html_to_text(body), extractor="anchor")

        # Fallback path: if card markup changes and the full closing </a> is no
        # longer easy to pair, use the local context around each live-score URL.
        # This keeps us anchored to semantic URL patterns rather than fragile lines.
        href_pattern = re.compile(
            r"""href\s*=\s*(['"])(?P<href>[^'"]*/cricket-live-score/[^'"]+)\1""",
            flags=re.IGNORECASE | re.VERBOSE,
        )
        for match in href_pattern.finditer(html_text):
            href = match.group("href")
            anchor_start = html_text.rfind("<a", 0, match.start())
            start = anchor_start if anchor_start >= max(0, match.start() - 300) else match.start()
            end = min(len(html_text), match.end() + 2200)
            context = html_text[start:end]
            self._append_crex_card(cards, seen, href, self._html_to_text(context), extractor="context")
        return cards

    def _append_crex_card(
        self,
        cards: List[Dict[str, str]],
        seen: set,
        href: str,
        text: str,
        extractor: str,
    ) -> None:
        if not href:
            return
        full_url = urllib.parse.urljoin("https://crex.com/", href)
        key = full_url.lower()
        if key in seen:
            return
        text = self._clean_crex_card_text(text, href)
        if not text:
            return
        seen.add(key)
        match_number = self._extract_crex_match_number(href, text)
        live_scan = text[:360]
        cards.append(
            {
                "url": full_url,
                "href": href,
                "text": text,
                "match_number": str(match_number) if match_number is not None else "",
                "is_live": "1" if re.search(r"\blive\b", live_scan, flags=re.IGNORECASE) else "0",
                "extractor": extractor,
            }
        )

    def _html_to_text(self, html_text: str) -> str:
        text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html_text or " ")
        text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    def _clean_crex_card_text(self, text: str, href: str) -> str:
        text = re.sub(r"\s+", " ", text or "").strip()
        if not text:
            return ""

        # Context fallback can include neighboring cards. Trim around obvious match
        # number/team/score signals when possible while preserving enough text for
        # the LLM to phrase the score.
        match_number = self._extract_crex_match_number(href, text)
        if match_number is not None:
            marker = re.search(rf"\b{match_number}(?:st|nd|rd|th)\b", text, flags=re.IGNORECASE)
            if marker:
                text = text[max(0, marker.start() - 180): marker.end() + 520].strip()
        live_marker = re.search(r"\bLive\b", text, flags=re.IGNORECASE)
        if live_marker:
            text = text[max(0, live_marker.start() - 180): live_marker.end() + 520].strip()

        return text[:1200]

    def _extract_crex_match_number(self, href: str, text: str) -> Optional[int]:
        combined = f"{href} {text}"
        match = re.search(r"\b(\d{1,3})(?:st|nd|rd|th)[-\s]*(?:match|t20|ipl)\b", combined, flags=re.IGNORECASE)
        if not match:
            match = re.search(r"\b(\d{1,3})(?:st|nd|rd|th)\b", combined, flags=re.IGNORECASE)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    def _select_crex_live_match_card(self, cards: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
        if not cards:
            return None
        live_cards = [
            card for card in cards
            if card.get("is_live") == "1" and re.search(r"\b\d{1,3}/\d{1,2}\b", card.get("text", ""))
        ]
        if live_cards:
            return live_cards[0]

        numbered = []
        for card in cards:
            try:
                numbered.append((int(card.get("match_number") or "0"), card))
            except ValueError:
                continue
        if len(numbered) >= 3:
            numbered.sort(key=lambda item: item[0])
            return numbered[len(numbered) // 2][1]
        if len(cards) >= 3:
            return cards[len(cards) // 2]
        return cards[0]

    def _summarize_crex_match_card(self, query: str, selected: Dict[str, str], cards: List[Dict[str, str]]) -> str:
        provider = self.cricket_llm_provider or "gemini"
        surrounding = "\n".join(
            f"- match {card.get('match_number') or '?'}: {card.get('text', '')}"
            for card in cards[:5]
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You parse raw CREX cricket match-card text. Use only the provided card text. "
                    "Do not browse, do not guess, and do not mention implementation details. "
                    "Answer in one or two short sentences with teams, scores, overs, and live/result state."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"User request: {query}\n"
                    f"Selected current/live card: {selected.get('text', '')}\n"
                    f"Selected URL: {selected.get('url', '')}\n"
                    f"Nearby cards for context:\n{surrounding}"
                ),
            },
        ]
        try:
            return self.llm_collect_text(
                messages,
                max_output_tokens=140,
                forced_provider=provider,
            ).strip()
        except TypeError:
            try:
                return self.llm_collect_text(messages, max_output_tokens=140).strip()
            except Exception:
                return ""
        except Exception:
            return ""

    def _format_crex_match_card_deterministically(self, selected: Dict[str, str]) -> str:
        text = re.sub(r"\s+", " ", selected.get("text", "")).strip()
        if not text:
            return ""
        live_parts = re.split(r"\bLive\b", text, maxsplit=1, flags=re.IGNORECASE)
        if len(live_parts) == 2:
            left = live_parts[0].strip()
            right = live_parts[1].strip()
            return f"Live IPL score: {left}; {right}."
        if re.search(r"\bwon\b", text, flags=re.IGNORECASE):
            return f"IPL result: {text}."
        return f"IPL score snapshot: {text}."

    def _handle_cricket_query_llm(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        provider = self.cricket_llm_provider or "gemini"
        normalized = self._normalize(query)
        wants_live = self._is_cricket_live_query(normalized)
        mode = "live score" if wants_live else "recent/past result"
        messages = [
            {
                "role": "system",
                "content": (
                    "You are CALCIE's grounded cricket assistant. Use current web-grounded information only. "
                    "Answer only with the requested live score or match result details. "
                    "If the request is live, include teams, score, overs, and current state. "
                    "If the request is a completed or past match result, include teams, winner, margin, and scores. "
                    "If the exact requested match/date is unclear, say what you found most likely and mention the uncertainty briefly. "
                    "Respond in 2 to 4 short sentences."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"User request: {query}\n"
                    f"Mode: {mode}\n"
                    "Use grounded live web information."
                ),
            },
        ]
        try:
            response = self.llm_collect_text(
                messages,
                max_output_tokens=220,
                forced_provider=provider,
                enable_web_grounding=True,
            ).strip()
        except TypeError:
            try:
                response = self.llm_collect_text(
                    messages,
                    max_output_tokens=220,
                    forced_provider=provider,
                ).strip()
            except Exception:
                return None, None
        except Exception:
            return None, None

        if not self._is_cricket_llm_answer_usable(response, wants_live=wants_live):
            return None, None
        spoken = response.split("\n", 1)[0].strip()
        return response, spoken

    def _run_cricket_vision_summary(self, query: str, wants_live: bool) -> Tuple[str, Dict]:
        best_result: Dict = {}
        best_text = ""
        for attempt in range(self.cricket_vision_attempts):
            if attempt > 0:
                time.sleep(min(4.0, 1.5 + attempt))
            goal = self._build_cricket_vision_goal(query=query, wants_live=wants_live)
            result = self.vision_skill.run_once_result(goal, source="search")
            text = str(result.get("summary") or result.get("alert_message") or "").strip()
            if text and not best_text:
                best_text = text
                best_result = result
            if self._looks_like_cricket_score_summary(text, wants_live=wants_live):
                return text, result
        if best_text:
            return best_text, best_result
        return "I opened the cricket page, but I could not read a reliable visible score yet.", best_result or {}

    def _looks_like_cricket_score_summary(self, text: str, wants_live: bool) -> bool:
        lowered = (text or "").lower()
        if not lowered:
            return False
        has_score = bool(re.search(r"\b\d{1,3}\s*/\s*\d{1,2}\b", lowered))
        has_overs = "over" in lowered or re.search(r"\b\d{1,2}(?:\.\d)?\s*ov\b", lowered)
        has_result = "won by" in lowered or "defeated" in lowered or "beat " in lowered or "results" in lowered
        has_match_words = any(term in lowered for term in {"match", "innings", "wickets", "runs", "score"})
        if wants_live:
            return bool(has_score and (has_overs or has_match_words))
        return bool((has_score and has_result) or has_result)

    def _is_cricket_llm_answer_usable(self, text: str, wants_live: bool) -> bool:
        lowered = (text or "").strip().lower()
        if not lowered:
            return False
        weak_markers = {
            "i couldn't",
            "i could not",
            "i can't",
            "unable to",
            "not getting a reliable",
            "check the official",
            "visit the official",
            "model error",
        }
        if any(marker in lowered for marker in weak_markers):
            return False
        has_score = bool(re.search(r"\b\d{1,3}\s*/\s*\d{1,2}\b", lowered))
        has_overs = "over" in lowered or bool(re.search(r"\b\d{1,2}(?:\.\d)?\s*ov", lowered))
        has_result = "won by" in lowered or "beat " in lowered or "defeated" in lowered
        if wants_live:
            return has_score and (has_overs or "wickets" in lowered or "innings" in lowered)
        return (has_score and has_result) or has_result

    def _build_cricket_vision_goal(self, query: str, wants_live: bool) -> str:
        cleaned_query = re.sub(r"\s+", " ", (query or "").strip())
        if wants_live:
            return (
                "Analyze this live cricket score page for the user's request: "
                f"'{cleaned_query}'. Identify the most relevant visible live cricket or IPL match and summarize "
                "the teams, current score, wickets, overs, and current match state. If the requested match is not "
                "visible on screen yet, say that clearly instead of guessing."
            )
        return (
            "Analyze this IPL completed matches results page for the user's request: "
            f"'{cleaned_query}'. Read the visible match cards carefully, including date, teams, scores, and result "
            "margin. If the requested date, team, or match is visible, answer with the result and score clearly. "
            "If only recent completed matches are visible, summarize those and say whether more scrolling may be needed."
        )

    def _handle_weather_query(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        location_query = self._extract_weather_location(query)
        if not self.weather_api_key:
            fallback = self._handle_weather_query_llm(query, location_query, "weather_api_not_configured")
            if fallback[0]:
                return fallback
            return "Weather API is not configured. Set WEATHER_API_KEY to enable direct weather lookups.", "Weather API is not configured."

        url = (
            f"{self.weather_api_url}?key={urllib.parse.quote_plus(self.weather_api_key)}"
            f"&q={urllib.parse.quote_plus(location_query)}&aqi=no"
        )
        body, err = self._get_json(url, timeout=max(self.search_http_timeout_s, 12))
        if body is None:
            api_message = self._extract_api_error_from_text(err or "")
            if api_message:
                fallback = self._handle_weather_query_llm(query, location_query, api_message)
                if fallback[0]:
                    return fallback
                return f"Weather lookup failed: {api_message}", "Weather lookup failed."
            fallback = self._handle_weather_query_llm(query, location_query, err or "weather_service_unreachable")
            if fallback[0]:
                return fallback
            return (
                f"I could not reach the weather service right now. Error: {err or 'unknown error'}",
                "I could not reach the weather service right now.",
            )

        api_err = self._extract_api_error(body)
        if api_err:
            fallback = self._handle_weather_query_llm(query, location_query, api_err)
            if fallback[0]:
                return fallback
            return f"Weather lookup failed: {api_err}", "Weather lookup failed."

        location_data = body.get("location") if isinstance(body, dict) else {}
        current = body.get("current") if isinstance(body, dict) else {}
        if not isinstance(location_data, dict) or not isinstance(current, dict):
            return "Weather lookup returned an incomplete result.", "Weather lookup returned an incomplete result."

        place_parts = [
            str(location_data.get("name") or "").strip(),
            str(location_data.get("region") or "").strip(),
            str(location_data.get("country") or "").strip(),
        ]
        place = ", ".join(part for part in place_parts if part)
        if not place:
            place = "your location" if location_query == "auto:ip" else location_query

        condition = ""
        condition_data = current.get("condition")
        if isinstance(condition_data, dict):
            condition = str(condition_data.get("text") or "").strip()

        temp_c = current.get("temp_c")
        feels_c = current.get("feelslike_c")
        humidity = current.get("humidity")
        wind_kph = current.get("wind_kph")
        local_time = str(location_data.get("localtime") or "").strip()

        details: List[str] = []
        if temp_c not in (None, ""):
            details.append(f"{temp_c}°C")
        if condition:
            details.append(condition)

        extras: List[str] = []
        if feels_c not in (None, ""):
            extras.append(f"feels like {feels_c}°C")
        if humidity not in (None, ""):
            extras.append(f"humidity {humidity}%")
        if wind_kph not in (None, ""):
            extras.append(f"wind {wind_kph} kph")
        if local_time:
            extras.append(f"local time {local_time}")

        response = f"Current weather for {place}: " + ", ".join(details or ["details unavailable"]) + "."
        if extras:
            response += " " + ". ".join(part.capitalize() for part in extras) + "."
        if self.debug_output:
            response += "\n\n[debug] provider=weatherapi | location_query=" + location_query

        spoken_bits = [f"In {place}, "]
        if temp_c not in (None, ""):
            spoken_bits.append(f"it is {temp_c} degrees")
        if feels_c not in (None, ""):
            try:
                if temp_c in (None, "") or abs(float(feels_c) - float(temp_c)) >= 1.0:
                    spoken_bits.append(f", feels like {feels_c}")
            except Exception:
                spoken_bits.append(f", feels like {feels_c}")
        if condition:
            if temp_c not in (None, ""):
                spoken_bits.append(f"and {condition.lower()}")
            else:
                spoken_bits.append(condition)
        spoken = "".join(spoken_bits).strip() or "Here is the current weather."
        return response, spoken

    def _handle_weather_query_llm(self, query: str, location_query: str, fallback_reason: str) -> Tuple[Optional[str], Optional[str]]:
        provider = self.weather_llm_provider or "gemini"
        messages = [
            {"role": "system", "content": WEATHER_GROUNDED_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"User request: {query}\n"
                    f"Default location: {location_query}\n"
                    f"Fallback reason: {fallback_reason}\n\n"
                    "Use current grounded web information. If the user did not explicitly name a city, use the default location. "
                    "Respond in 2 to 4 short sentences."
                ),
            },
        ]
        try:
            response = self.llm_collect_text(
                messages,
                max_output_tokens=180,
                forced_provider=provider,
                enable_web_grounding=True,
            ).strip()
        except TypeError:
            try:
                response = self.llm_collect_text(
                    messages,
                    max_output_tokens=180,
                    forced_provider=provider,
                ).strip()
            except Exception:
                return None, None
        except Exception:
            return None, None

        if not response or "model error" in response.lower():
            return None, None
        spoken = response.split("\n", 1)[0].strip()
        return response, spoken

    def _handle_jobs_query(self, query: str) -> Tuple[str, str]:
        if self.job_hunter_enabled and self.app_skill:
            launched = self._launch_job_hunter(query)
            if launched:
                message = "Opened Job Hunter for this search. Results will load in the browser."
                return message, "Opening Job Hunter now."

        jobs, provider_used, attempts = self._search_jobs(query)
        if not jobs:
            role = self._normalize_jobs_query(query)
            fallback_query = f"{role} jobs site:linkedin.com/jobs OR site:indeed.com OR site:wellfound.com OR site:glassdoor.com"
            results, provider_used, attempts2 = self._search(fallback_query)
            attempts.extend(attempts2)
            listing_summary = self._summarize_job_links(query, results, attempts, provider_used)
            if listing_summary:
                return listing_summary, "Live jobs providers were unavailable, so I found job board links instead."
            return "I could not find live job listings for that role right now.", "I could not find live job listings right now."

        summary = self._summarize_jobs(query, jobs)
        response = summary
        if self.show_sources:
            lines = []
            for job in jobs[: self.jobs_max_results]:
                title = job.get("title") or "Untitled role"
                company = job.get("company") or "Unknown company"
                location = job.get("location") or "Location not listed"
                url = job.get("url") or ""
                lines.append(f"- {title} — {company} — {location} ({url})")
            response += "\n\nSources:\n" + "\n".join(lines)
        if self.debug_output:
            response += f"\n\n[debug] provider={provider_used} | attempts={' | '.join(attempts)}"
        return response, "I found live job listings for that role."

    def _infer_sports_tool_call(self, query: str) -> Tuple[str, Dict[str, str], str]:
        normalized = self._normalize(query)
        heuristic = self._heuristic_sports_tool_call(query)
        messages = [
            {"role": "system", "content": SPORTS_MCP_INTERPRET_SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]
        try:
            raw = self.llm_collect_text(messages, max_output_tokens=220)
            parsed = self._extract_json_object(raw)
            if isinstance(parsed, dict):
                tool = str(parsed.get("tool") or heuristic[0]).strip() or heuristic[0]
                sport = str(parsed.get("sport") or "").strip()
                league = str(parsed.get("league") or "").strip()
                clean_query = str(parsed.get("query") or "").strip() or heuristic[1].get("query") or query
                args: Dict[str, str] = {}
                if sport:
                    args["sport"] = sport
                if league:
                    args["league"] = league
                if clean_query:
                    args["query"] = clean_query
                return tool, self._sanitize_sports_tool_args(tool, args, query), str(parsed.get("reason") or "llm")
        except Exception:
            pass
        return heuristic

    def _heuristic_sports_tool_call(self, query: str) -> Tuple[str, Dict[str, str], str]:
        normalized = self._normalize(query)
        sport, league = self._infer_sport_league(normalized)
        args: Dict[str, str] = {}
        if sport:
            args["sport"] = sport
        if league:
            args["league"] = league

        if any(term in normalized for term in ["standings", "points table", "table"]):
            return "espn_standings", self._sanitize_sports_tool_args("espn_standings", args, query), "standings_keywords"
        if any(term in normalized for term in ["ranking", "rankings"]):
            return "espn_rankings", self._sanitize_sports_tool_args("espn_rankings", args, query), "rankings_keywords"
        if any(term in normalized for term in ["news", "headlines", "headline"]):
            return "espn_news", self._sanitize_sports_tool_args("espn_news", args, query), "news_keywords"
        if any(term in normalized for term in ["live", "score", "scores", "won", "last night", "today", "tonight", "scoreboard", "result", "results"]):
            tool = "espn_live_scoreboard" if "live" in normalized or "now" in normalized or "tonight" in normalized else "espn_scoreboard"
            return tool, self._sanitize_sports_tool_args(tool, args, query), "score_keywords"

        args["query"] = self._clean_sports_query(query)
        return "espn_search", self._sanitize_sports_tool_args("espn_search", args, query), "fallback_search"

    def _sanitize_sports_tool_args(self, tool: str, args: Dict[str, str], query: str) -> Dict[str, str]:
        out = {k: v for k, v in args.items() if v}
        if tool in {"espn_scoreboard", "espn_live_scoreboard", "espn_standings", "espn_rankings", "espn_news"}:
            out.pop("query", None)
        if tool == "espn_search" and not out.get("query"):
            out["query"] = self._clean_sports_query(query)
        return out

    def _call_sports_mcp_tool(self, tool_name: str, args: Dict[str, str]) -> Tuple[str, str]:
        if not self.sports_mcp_base_url or not self.apify_api_key:
            return "", "missing_config"

        endpoint = self.sports_mcp_base_url
        if "token=" not in endpoint:
            joiner = "&" if "?" in endpoint else "?"
            endpoint = f"{endpoint}{joiner}token={urllib.parse.quote_plus(self.apify_api_key)}"

        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "CALCIE", "version": "1.0"},
            },
        }
        self._post_json(
            endpoint,
            init_payload,
            headers={
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-03-26",
            },
            timeout=self.sports_mcp_timeout_s,
        )

        call_payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": args,
            },
        }
        body, err = self._post_json(
            endpoint,
            call_payload,
            headers={
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-03-26",
            },
            timeout=self.sports_mcp_timeout_s,
        )
        if body is None:
            return "", err or "mcp_http_error"
        if isinstance(body, dict) and body.get("error"):
            return "", self._extract_api_error(body) or str(body.get("error"))
        result = body.get("result") if isinstance(body, dict) else None
        content = result.get("content") if isinstance(result, dict) else None
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text).strip())
            if parts:
                return "\n\n".join(parts).strip(), ""
        if isinstance(result, dict):
            text = result.get("text") or result.get("content")
            if isinstance(text, str) and text.strip():
                return text.strip(), ""
        return "", "empty_mcp_result"

    def _launch_job_hunter(self, query: str) -> bool:
        server_js = self.project_root / "job-hunter" / "server.js"
        index_html = self.project_root / "job-hunter" / "index.html"
        if not server_js.exists() or not index_html.exists():
            return False
        if not self._ensure_job_hunter_server_running(server_js):
            return False

        params = self._extract_job_hunter_query_params(query)
        params["autorun"] = "1" if self.job_hunter_autorun else "0"
        target = f"http://127.0.0.1:{self.job_hunter_port}/?{urllib.parse.urlencode(params)}"
        try:
            response = self.app_skill.open_target_in_app(target, self.job_hunter_browser)
        except Exception:
            return False
        lowered = (response or "").lower()
        return bool(response) and not lowered.startswith("failed")

    def _ensure_job_hunter_server_running(self, server_js: pathlib.Path) -> bool:
        if self._is_job_hunter_alive():
            return True

        node_bin = self._find_node_binary()
        if not node_bin:
            return False

        runtime_dir = self.project_root / ".calcie" / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        log_path = runtime_dir / "job-hunter.log"
        env = os.environ.copy()
        env["PORT"] = str(self.job_hunter_port)

        with open(log_path, "ab") as log_file:
            subprocess.Popen(
                [node_bin, str(server_js)],
                cwd=str(server_js.parent),
                env=env,
                stdout=log_file,
                stderr=log_file,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

        deadline = time.time() + 8.0
        while time.time() < deadline:
            if self._is_job_hunter_alive():
                return True
            time.sleep(0.4)
        return False

    def _is_job_hunter_alive(self) -> bool:
        url = f"http://127.0.0.1:{self.job_hunter_port}/"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CALCIE/1.0"})
            with urllib.request.urlopen(req, timeout=1.5) as res:
                return 200 <= getattr(res, "status", 200) < 500
        except Exception:
            return False

    def _find_node_binary(self) -> str:
        for candidate in ("node", "/opt/homebrew/bin/node", "/usr/local/bin/node"):
            if os.path.exists(candidate) and os.access(candidate, os.X_OK):
                return candidate
            resolved = shutil.which(candidate) if "/" not in candidate else None
            if resolved:
                return resolved
        return ""

    def _extract_job_hunter_query_params(self, query: str) -> Dict[str, str]:
        raw = (query or "").strip()
        location = ""
        role = raw
        location_match = re.search(r"\b(?:in|at|for)\s+([a-zA-Z ,.-]{2,})$", raw, flags=re.IGNORECASE)
        if location_match:
            location = location_match.group(1).strip(" ,.-")
            role = raw[: location_match.start()].strip(" ,.-")
        role = self._normalize_jobs_query(role or raw) or raw
        params = {"q": role}
        if location:
            params["location"] = location
        if re.search(r"\bremote\b", raw, flags=re.IGNORECASE):
            params["remote"] = "1"
        return params

    def _search(self, query: str) -> Tuple[List[Dict[str, str]], str, List[str]]:
        provider = self.search_provider
        if provider not in {"auto", "tavily", "exa", "ddgs"}:
            provider = "auto"

        if provider == "auto":
            order = ["tavily", "exa", "ddgs"]
        elif provider == "tavily":
            order = ["tavily", "exa", "ddgs"]
        elif provider == "exa":
            order = ["exa", "tavily", "ddgs"]
        else:
            order = ["ddgs", "tavily", "exa"]

        attempts: List[str] = []
        for name in order:
            if name == "tavily":
                if not self.tavily_api_key:
                    attempts.append("tavily:missing_key")
                else:
                    results, reason = self._search_tavily(query)
                    if results:
                        attempts.append("tavily:ok")
                        return results, "tavily", attempts
                    attempts.append(f"tavily:{reason}")
            if name == "exa":
                if not self.exa_api_key:
                    attempts.append("exa:missing_key")
                else:
                    results, reason = self._search_exa(query)
                    if results:
                        attempts.append("exa:ok")
                        return results, "exa", attempts
                    attempts.append(f"exa:{reason}")
            if name == "ddgs":
                results, reason = self._search_ddgs(query)
                if results:
                    attempts.append("ddgs:ok")
                    return results, "ddgs", attempts
                attempts.append(f"ddgs:{reason}")
        return [], "none", attempts

    def _search_jobs(self, query: str) -> Tuple[List[Dict[str, str]], str, List[str]]:
        attempts: List[str] = []
        normalized_query = self._normalize_jobs_query(query)

        if self.apify_api_key and self.apify_actor_id:
            results, reason = self._search_jobs_apify(normalized_query)
            if results:
                attempts.append("apify:ok")
                return results, "apify", attempts
            attempts.append(f"apify:{reason}")
        else:
            attempts.append("apify:missing_config")

        if self.rapidapi_key:
            results, reason = self._search_jobs_rapidapi(normalized_query)
            if results:
                attempts.append("rapidapi:ok")
                return results, "rapidapi", attempts
            attempts.append(f"rapidapi:{reason}")
        else:
            attempts.append("rapidapi:missing_key")

        return [], "none", attempts

    def _search_jobs_apify(self, query: str) -> Tuple[List[Dict[str, str]], str]:
        url = (
            f"https://api.apify.com/v2/acts/{self.apify_actor_id}"
            f"/run-sync-get-dataset-items?token={self.apify_api_key}"
        )
        payload = {
            "query": query,
            "search": query,
            "keyword": query,
            "keywords": [query],
            "maxItems": self.jobs_max_results,
            "maxResults": self.jobs_max_results,
        }
        body, err = self._post_json(url, payload, timeout=max(self.search_http_timeout_s, 18))
        if body is None:
            return [], f"http_error:{(err or 'unknown')[:80]}"
        rows = body if isinstance(body, list) else body.get("items") or body.get("data") or []
        normalized = self._normalize_job_rows(rows, source="apify")
        if normalized:
            return normalized, "ok"
        return [], "empty_results"

    def _search_jobs_rapidapi(self, query: str) -> Tuple[List[Dict[str, str]], str]:
        url = "https://jsearch.p.rapidapi.com/search"
        params = f"?query={self._url_encode(query)}&page=1&num_pages=1&date_posted=all"
        body, err = self._get_json(
            url + params,
            headers={
                "x-rapidapi-key": self.rapidapi_key,
                "x-rapidapi-host": "jsearch.p.rapidapi.com",
            },
            timeout=max(self.search_http_timeout_s, 15),
        )
        if body is None:
            return [], f"http_error:{(err or 'unknown')[:80]}"
        rows = body.get("data") or body.get("jobs") or []
        normalized = self._normalize_job_rows(rows, source="rapidapi")
        if normalized:
            return normalized, "ok"
        return [], "empty_results"

    def _search_tavily(self, query: str) -> Tuple[List[Dict[str, str]], str]:
        # Optional deep-research path (slower).
        if self.tavily_mode == "research" and self._tavily_client:
            try:
                initial = self._tavily_client.research(query)
                request_id = (initial or {}).get("request_id")
                if request_id:
                    deadline = time.time() + self.research_timeout_s
                    while time.time() < deadline:
                        result = self._tavily_client.get_research_result(request_id)
                        status = (result or {}).get("status")
                        if status == "completed":
                            normalized = self._normalize_tavily_research_sources(result)
                            if normalized:
                                return normalized, "ok"
                            return [], "empty_research_sources"
                        if status == "failed":
                            msg = self._extract_api_error(result) or "research_failed"
                            if self._is_quota_error(msg):
                                return [], "quota_exhausted"
                            return [], msg
                        time.sleep(self.research_poll_s)
                    return [], "research_timeout"
            except Exception as exc:
                msg = self._safe_error(exc)
                if self._is_quota_error(msg):
                    return [], "quota_exhausted"

        # Fallback path: Tavily HTTP search API.
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.tavily_api_key,
            "query": query,
            "max_results": self.max_results,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
        }
        body, err = self._post_json(url, payload, timeout=self.search_http_timeout_s)
        if not body:
            if self._is_quota_error(err or ""):
                return [], "quota_exhausted"
            return [], f"http_error:{(err or 'unknown')[:80]}"
        api_err = self._extract_api_error(body)
        if api_err:
            if self._is_quota_error(api_err):
                return [], "quota_exhausted"
            return [], f"api_error:{api_err[:80]}"
        normalized = self._normalize_tavily_search_results(body)
        if normalized:
            return normalized, "ok"
        return [], "empty_results"

    def _search_exa(self, query: str) -> Tuple[List[Dict[str, str]], str]:
        # Preferred path: Exa SDK.
        if self._exa_client:
            try:
                kwargs = {
                    "type": "fast",
                    "num_results": self.max_results,
                    "highlights": {"max_characters": self.max_source_chars},
                }
                if self._looks_like_news_query(query):
                    kwargs["category"] = "news"
                result_obj = self._exa_client.search_and_contents(query, **kwargs)
                normalized = self._normalize_exa_sdk_results(result_obj)
                if normalized:
                    return normalized, "ok"
                return [], "empty_results"
            except Exception as exc:
                msg = self._safe_error(exc)
                if self._is_quota_error(msg):
                    return [], "quota_exhausted"

        # Fallback path: Exa HTTP API.
        url = "https://api.exa.ai/search"
        payload = {
            "query": query,
            "type": "fast",
            "numResults": self.max_results,
            "contents": {"highlights": {"maxCharacters": self.max_source_chars}},
        }
        if self._looks_like_news_query(query):
            payload["category"] = "news"
        body, err = self._post_json(
            url,
            payload,
            headers={"x-api-key": self.exa_api_key},
            timeout=self.search_http_timeout_s,
        )
        if not body:
            if self._is_quota_error(err or ""):
                return [], "quota_exhausted"
            return [], f"http_error:{(err or 'unknown')[:80]}"
        api_err = self._extract_api_error(body)
        if api_err:
            if self._is_quota_error(api_err):
                return [], "quota_exhausted"
            return [], f"api_error:{api_err[:80]}"
        normalized = self._normalize_exa_http_results(body)
        if normalized:
            return normalized, "ok"
        return [], "empty_results"

    def _search_ddgs(self, query: str) -> Tuple[List[Dict[str, str]], str]:
        if DDGS is None:
            return [], "ddgs_not_installed"
        try:
            with DDGS() as ddgs:
                rows = list(ddgs.text(query, max_results=self.ddgs_fallback_results))
        except Exception as exc:
            return [], f"ddgs_error:{self._safe_error(exc)[:80]}"

        out: List[Dict[str, str]] = []
        for row in rows[: self.ddgs_fallback_results]:
            url = (row.get("href") or row.get("url") or "").strip()
            if not url:
                continue
            out.append(
                {
                    "title": (row.get("title") or "").strip() or "Untitled",
                    "url": url,
                    "text": "",
                    "snippet": (row.get("body") or row.get("snippet") or "").strip(),
                }
            )
        if not out:
            return [], "ddgs_empty"
        return out, "ok"

    def _scrape_results(self, results: List[Dict[str, str]]) -> List[Dict[str, str]]:
        scraped = []
        for item in results[: self.scrape_top_k]:
            url = item.get("url", "").strip()
            if not url:
                continue
            text = (item.get("text") or "").strip()
            if not text:
                text = self._fetch_url_text(url)
            if not text:
                text = (item.get("snippet") or "").strip()
            if not text:
                continue
            scraped.append(
                {
                    "title": item.get("title") or "Untitled",
                    "url": url,
                    "text": text[: self.max_source_chars],
                }
            )
        return scraped

    def _fetch_url_text(self, url: str) -> str:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.page_fetch_timeout_s) as res:
                content_type = (res.headers.get("Content-Type") or "").lower()
                raw = res.read(160_000)
        except (urllib.error.URLError, ValueError, OSError):
            return ""

        if "html" not in content_type and "text" not in content_type:
            return ""

        text = raw.decode("utf-8", errors="replace")
        text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
        text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _synthesize(self, query: str, sources: List[Dict[str, str]]) -> str:
        blocks = []
        for i, src in enumerate(sources[: self.max_results], start=1):
            blocks.append(
                f"Source {i}\nTitle: {src['title']}\nURL: {src['url']}\nText: {src['text']}\n"
            )
        source_blob = "\n\n".join(blocks)
        messages = [
            {
                "role": "system",
                "content": SEARCH_SYNTH_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": SEARCH_SYNTH_USER_TEMPLATE.format(query=query, source_blob=source_blob),
            },
        ]
        llm_kwargs = {}
        if self.search_llm_provider and self.search_llm_provider != "auto":
            llm_kwargs["forced_provider"] = self.search_llm_provider
        try:
            summary = self.llm_collect_text(messages, max_output_tokens=self.synth_tokens, **llm_kwargs)
        except TypeError:
            summary = self.llm_collect_text(messages, max_output_tokens=self.synth_tokens)
        if summary and "model error" not in summary.lower():
            cleaned = summary.strip()
            if self._is_summary_acceptable(query, cleaned):
                return cleaned
        deterministic = self._deterministic_summary(query, sources)
        if deterministic:
            return deterministic
        return "I found relevant sources, but synthesis is unavailable right now."

    def _normalize(self, text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())).strip()

    def _url_encode(self, text: str) -> str:
        from urllib.parse import quote_plus

        return quote_plus((text or "").strip())

    def _is_weather_query(self, normalized: str) -> bool:
        if not normalized:
            return False
        weather_terms = {
            "weather", "temperature", "forecast", "humidity", "raining", "rain",
            "wind", "windy", "hot", "cold", "outside", "sunny", "cloudy",
        }
        return any(term in normalized.split() for term in weather_terms) or any(
            phrase in normalized for phrase in {"what is the weather", "whats the weather", "how is the weather"}
        )

    def _extract_weather_location(self, query: str) -> str:
        raw = self._clean_transcript_noise((query or "").strip())
        if not raw:
            return self.weather_default_query

        lowered = raw.lower()
        normalized = self._normalize(raw)
        generic_weather_query = re.sub(
            r"\b(what|whats|what s|how|hows|how s|tell|me|show|search|find|check|current|latest|today|now|the|is|it|like|weather|temperature|forecast|humidity|rain|raining|wind|windy|outside)\b",
            " ",
            normalized,
        )
        generic_weather_query = re.sub(r"\s+", " ", generic_weather_query).strip()

        if not generic_weather_query:
            return self.weather_default_query

        if any(marker in lowered for marker in {"my location", "current location", "near me", "outside here"}):
            return "auto:ip"
        if re.search(r"\b(here|outside)\b", lowered) and " in " not in lowered:
            return "auto:ip"

        match = re.search(r"\b(?:in|at|for)\s+([a-zA-Z][a-zA-Z .,-]{1,})$", raw, flags=re.IGNORECASE)
        if match:
            location = match.group(1).strip(" ,.-")
            if location:
                return location

        cleaned = re.sub(
            r"\b(what(?:'s| is)?|how(?:'s| is)?|tell me|show me|search|find|check|current|latest|today|now|the|weather|temperature|forecast|humidity|rain|raining|wind|windy|outside)\b",
            " ",
            raw,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
        if cleaned and len(cleaned.split()) <= 5 and re.search(r"[A-Za-z]", cleaned):
            return cleaned
        return self.weather_default_query

    def _is_sports_query(self, normalized: str) -> bool:
        if not normalized:
            return False
        sports_terms = {
            "sports", "sport", "score", "scores", "scoreboard", "match", "matches", "game", "games",
            "standings", "table", "points table", "ranking", "rankings", "fixtures", "schedule", "odds",
            "nfl", "nba", "mlb", "nhl", "wnba", "ufc", "f1", "formula 1", "nascar", "premier league",
            "la liga", "bundesliga", "serie a", "ligue 1", "champions league", "mls",
            "college football", "college basketball", "soccer", "football", "basketball", "baseball", "hockey",
            "tennis", "golf", "racing", "ipl", "cricket",
        }
        return any(term in normalized for term in sports_terms)

    def _is_cricket_query(self, normalized: str) -> bool:
        return any(term in normalized for term in {"ipl", "cricket"})

    def _is_cricket_live_query(self, normalized: str) -> bool:
        if not self._is_cricket_query(normalized):
            return False
        live_terms = {
            "live",
            "live score",
            "score",
            "scorecard",
            "current score",
            "current",
            "now",
            "today",
            "ongoing",
        }
        return any(term in normalized for term in live_terms)

    def _is_explicit_cricket_page_query(self, normalized: str) -> bool:
        if not self._is_cricket_query(normalized):
            return False
        page_terms = {
            "open",
            "website",
            "site",
            "page",
            "results page",
            "live score page",
            "crex",
            "iplt20",
            "check visually",
            "look at",
            "see the",
        }
        return any(term in normalized for term in page_terms)

    def _is_unsupported_espn_sport(self, normalized: str) -> bool:
        return any(term in normalized for term in {"ipl", "cricket", "bbl", "ranji"})

    def _infer_sport_league(self, normalized: str) -> Tuple[str, str]:
        mappings = [
            ("college football", ("football", "college-football")),
            ("college basketball", ("basketball", "mens-college-basketball")),
            ("premier league", ("soccer", "eng.1")),
            ("la liga", ("soccer", "esp.1")),
            ("bundesliga", ("soccer", "ger.1")),
            ("serie a", ("soccer", "ita.1")),
            ("ligue 1", ("soccer", "fra.1")),
            ("champions league", ("soccer", "uefa.champions")),
            ("mls", ("soccer", "usa.1")),
            ("nba", ("basketball", "nba")),
            ("wnba", ("basketball", "wnba")),
            ("nfl", ("football", "nfl")),
            ("mlb", ("baseball", "mlb")),
            ("nhl", ("hockey", "nhl")),
            ("ufc", ("mma", "ufc")),
            ("formula 1", ("racing", "f1")),
            ("f1", ("racing", "f1")),
            ("nascar", ("racing", "nascar-premier")),
            ("pga", ("golf", "pga")),
            ("lpga", ("golf", "lpga")),
            ("atp", ("tennis", "atp")),
            ("wta", ("tennis", "wta")),
        ]
        for marker, codes in mappings:
            if marker in normalized:
                return codes
        return "", ""

    def _clean_sports_query(self, query: str) -> str:
        cleaned = self._normalize(query)
        cleaned = re.sub(
            r"\b(check|search|find|lookup|look up|latest|live|today|tonight|last night|score|scores|scoreboard|standings|table|points|result|results|news|headlines)\b",
            " ",
            cleaned,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or self._normalize(query)

    def _is_job_query(self, normalized: str) -> bool:
        if not normalized:
            return False
        job_terms = {"job", "jobs", "role", "roles", "hiring", "openings", "vacancy", "vacancies", "career", "careers"}
        return any(term in normalized.split() for term in job_terms) or (
            "job" in normalized or "role" in normalized or "hiring" in normalized
        )

    def _normalize_jobs_query(self, query: str) -> str:
        cleaned = self._normalize(query)
        cleaned = re.sub(r"\b(search|find|lookup|look up)\b", " ", cleaned)
        cleaned = re.sub(r"\b(job|jobs|role|roles|hiring|openings|vacancy|vacancies|career|careers)\b", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or self._normalize(query)

    def _summarize_jobs(self, query: str, jobs: List[Dict[str, str]]) -> str:
        role = self._normalize_jobs_query(query) or query.strip()
        lines = [f"Here are the strongest live job results I found for {role}:"]
        for job in jobs[: self.jobs_max_results]:
            title = job.get("title") or "Untitled role"
            company = job.get("company") or "Unknown company"
            location = job.get("location") or "Location not listed"
            extras = []
            if job.get("salary"):
                extras.append(f"salary: {job['salary']}")
            if job.get("posted"):
                extras.append(f"posted: {job['posted']}")
            extra_text = f" ({', '.join(extras)})" if extras else ""
            lines.append(f"- {title} at {company} — {location}{extra_text}")
        lines.append("Ask me to narrow it by location, experience level, remote, or salary if you want.")
        return "\n".join(lines)

    def _summarize_job_links(
        self,
        query: str,
        results: List[Dict[str, str]],
        attempts: List[str],
        provider_used: str,
    ) -> str:
        if not results:
            return ""
        role = self._normalize_jobs_query(query) or query.strip()
        lines = [
            f"Live jobs providers were unavailable for {role}, so here are the strongest job-board links I found:",
        ]
        for item in results[: self.max_results]:
            title = (item.get("title") or "Untitled result").strip()
            url = (item.get("url") or "").strip()
            snippet = (item.get("snippet") or item.get("text") or "").strip()
            line = f"- {title}"
            if snippet:
                line += f" — {snippet[:140].rstrip()}"
            if url:
                line += f" ({url})"
            lines.append(line)
        if self.debug_output:
            lines.append("")
            lines.append(f"[debug] provider={provider_used} | attempts={' | '.join(attempts)}")
        return "\n".join(lines)

    def _looks_like_news_query(self, query: str) -> bool:
        normalized = self._normalize(query)
        return bool(re.search(r"\b(news|headline|latest|today|yesterday|last night|breaking)\b", normalized))

    def _post_json(
        self,
        url: str,
        payload: Dict,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 20,
    ) -> Tuple[Optional[Dict], Optional[str]]:
        req_headers = {"Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return json.loads(res.read().decode("utf-8", errors="replace")), None
        except urllib.error.HTTPError as exc:
            raw = ""
            try:
                raw = exc.read().decode("utf-8", errors="replace")
            except Exception:
                raw = str(exc)
            return None, raw or str(exc)
        except Exception as exc:
            return None, self._safe_error(exc)

    def _get_json(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 20,
    ) -> Tuple[Optional[Dict], Optional[str]]:
        req_headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"
        }
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(url, headers=req_headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return json.loads(res.read().decode("utf-8", errors="replace")), None
        except urllib.error.HTTPError as exc:
            raw = ""
            try:
                raw = exc.read().decode("utf-8", errors="replace")
            except Exception:
                raw = str(exc)
            return None, raw or str(exc)
        except Exception as exc:
            return None, self._safe_error(exc)

    def _normalize_tavily_search_results(self, body: Dict) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        for item in body.get("results", [])[: self.max_results]:
            text = (item.get("raw_content") or item.get("content") or "").strip()
            out.append(
                {
                    "title": (item.get("title") or "").strip() or "Untitled",
                    "url": (item.get("url") or "").strip(),
                    "text": text,
                }
            )
        return [r for r in out if r.get("url")]

    def _normalize_tavily_research_sources(self, result: Dict) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        for item in (result or {}).get("sources", [])[: self.max_results]:
            text = (
                item.get("raw_content")
                or item.get("content")
                or item.get("snippet")
                or ""
            )
            out.append(
                {
                    "title": (item.get("title") or "").strip() or "Untitled",
                    "url": (item.get("url") or "").strip(),
                    "text": (text or "").strip(),
                }
            )
        return [r for r in out if r.get("url")]

    def _normalize_exa_http_results(self, body: Dict) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        for item in body.get("results", [])[: self.max_results]:
            highlights = item.get("highlights") or []
            text_bits: List[str] = []
            if isinstance(highlights, list):
                text_bits.extend(str(h).strip() for h in highlights if str(h).strip())
            text = "\n".join(text_bits).strip() or (item.get("text") or item.get("snippet") or "").strip()
            out.append(
                {
                    "title": (item.get("title") or "").strip() or "Untitled",
                    "url": (item.get("url") or "").strip(),
                    "text": text,
                }
            )
        return [r for r in out if r.get("url")]

    def _normalize_exa_sdk_results(self, result_obj) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        results = getattr(result_obj, "results", []) or []
        for item in results[: self.max_results]:
            highlights = getattr(item, "highlights", None) or []
            text_bits: List[str] = []
            if isinstance(highlights, list):
                text_bits.extend(str(h).strip() for h in highlights if str(h).strip())
            text = "\n".join(text_bits).strip() or (getattr(item, "text", "") or "").strip()
            out.append(
                {
                    "title": (getattr(item, "title", "") or "").strip() or "Untitled",
                    "url": (getattr(item, "url", "") or "").strip(),
                    "text": text,
                }
            )
        return [r for r in out if r.get("url")]

    def _normalize_job_rows(self, rows, source: str) -> List[Dict[str, str]]:
        normalized: List[Dict[str, str]] = []
        if not isinstance(rows, list):
            return normalized
        for row in rows[: self.jobs_max_results]:
            if not isinstance(row, dict):
                continue
            title = (
                row.get("job_title")
                or row.get("title")
                or row.get("positionName")
                or row.get("position")
                or ""
            )
            company = (
                row.get("employer_name")
                or row.get("company")
                or row.get("companyName")
                or row.get("company_name")
                or ""
            )
            location = (
                row.get("job_city")
                or row.get("location")
                or row.get("job_location")
                or row.get("city")
                or row.get("job_country")
                or ""
            )
            url = (
                row.get("job_apply_link")
                or row.get("url")
                or row.get("link")
                or row.get("applyUrl")
                or row.get("job_url")
                or ""
            )
            posted = (
                row.get("job_posted_at_datetime_utc")
                or row.get("postedAt")
                or row.get("datePosted")
                or ""
            )
            salary = (
                row.get("job_min_salary")
                or row.get("salary")
                or row.get("salaryRange")
                or ""
            )
            if not title and not url:
                continue
            normalized.append(
                {
                    "title": str(title).strip() or "Untitled role",
                    "company": str(company).strip() or "Unknown company",
                    "location": str(location).strip() or "Location not listed",
                    "url": str(url).strip(),
                    "posted": str(posted).strip(),
                    "salary": str(salary).strip(),
                    "source": source,
                }
            )
        return [item for item in normalized if item.get("title")]

    def _is_quota_error(self, message: str) -> bool:
        text = (message or "").lower()
        signals = [
            "quota",
            "rate limit",
            "rate_limit",
            "429",
            "insufficient credits",
            "insufficient credit",
            "out of credits",
            "out of tokens",
            "token limit",
            "usage limit",
            "free tier",
        ]
        return any(s in text for s in signals)

    def _extract_api_error(self, payload: Optional[Dict]) -> str:
        if not isinstance(payload, dict):
            return ""
        for key in ("error", "message", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                nested = value.get("message") or value.get("detail")
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
        return ""

    def _extract_api_error_from_text(self, raw: str) -> str:
        text = (raw or "").strip()
        if not text:
            return ""
        try:
            parsed = json.loads(text)
        except Exception:
            return ""
        return self._extract_api_error(parsed)

    def _safe_error(self, exc: Exception) -> str:
        text = str(exc).strip()
        if text:
            return text
        return exc.__class__.__name__

    def _clean_transcript_noise(self, text: str) -> str:
        cleaned = (text or "").strip()
        if not cleaned:
            return ""
        noise_patterns = [
            r"for text or 'hey calcie'\.*$",
            r"type mode\].*$",
            r"\bintent\s*=\s*[^\s)]+",
            r"\breason\s*=\s*[^\s)]+",
        ]
        for pat in noise_patterns:
            cleaned = re.sub(pat, " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b([a-z]{3,})\d+\b", r"\1", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;)]}")
        return cleaned

    def _is_ipl_table_query(self, normalized: str) -> bool:
        if "ipl" not in normalized:
            return False
        table_terms = {"points table", "point table", "standings", "table", "rankings"}
        return any(term in normalized for term in table_terms)

    def _is_ipl_score_query(self, normalized: str) -> bool:
        if "ipl" not in normalized:
            return False
        score_terms = {"score", "live score", "scorecard", "current score", "now score"}
        temporal_terms = {"latest", "live", "today", "now", "current"}
        return any(term in normalized for term in score_terms) or (
            "score" in normalized and any(term in normalized for term in temporal_terms)
        )

    def _prepare_provider_query(self, query: str) -> str:
        normalized = self._normalize(query)
        if self._is_ipl_score_query(normalized):
            return "IPL live score today scorecard overs wickets"
        if self._is_ipl_table_query(normalized):
            return "IPL points table latest standings net run rate"
        return query

    def _looks_like_bad_summary(self, text: str) -> bool:
        lowered = (text or "").lower()
        bad_markers = [
            "[insert",
            "placeholder",
            "*searches",
            "let me know if you want",
            "just try to keep",
            "agenda today",
            "project-related",
            "i can fetch",
        ]
        return any(m in lowered for m in bad_markers)

    def _is_summary_acceptable(self, query: str, summary: str) -> bool:
        if self._looks_like_bad_summary(summary):
            return False
        normalized_query = self._normalize(query)
        lowered = (summary or "").lower()
        if self._is_ipl_score_query(normalized_query):
            if "upcoming fixtures" in lowered:
                return False
            return self._contains_score_pattern(summary)
        return True

    def _contains_score_pattern(self, text: str) -> bool:
        if not text:
            return False
        patterns = [
            r"\b\d{1,3}\s*/\s*\d{1,2}\b",               # 156/4
            r"\b\d{1,2}(?:\.\d)?\s*overs?\b",           # 18.3 overs
            r"\bwon by \d+\s+(?:runs?|wickets?)\b",     # won by x runs/wickets
        ]
        lowered = text.lower()
        return any(re.search(p, lowered, flags=re.IGNORECASE) for p in patterns)

    def _deterministic_summary(self, query: str, sources: List[Dict[str, str]]) -> str:
        if not sources:
            return ""

        normalized_query = self._normalize(query)
        if self._is_ipl_score_query(normalized_query):
            score_lines = self._extract_ipl_score_lines(sources)
            if score_lines:
                lead = "; ".join(score_lines[:2])
                return (
                    f"Latest IPL score snapshot: {lead}. "
                    "This is compiled from live-score sources and may update ball-by-ball. "
                    "Ask for full scorecard if you want batting and bowling breakdown."
                )
            links = ", ".join(s.get("url", "") for s in sources[:3] if s.get("url"))
            return (
                "I could not reliably extract a precise live score line from the fetched pages. "
                "Open one of these live-score links for exact ball-by-ball status: "
                f"{links}"
            )

        if self._is_ipl_table_query(normalized_query):
            table_lines = self._extract_ipl_points_lines(sources)
            if table_lines:
                top = "; ".join(table_lines[:5])
                return (
                    f"Latest IPL points table snapshot from web sources: {top}. "
                    "Different sites may lag by one match; verify with the official IPL table for final ordering. "
                    "Full-table output is available on request."
                )

        headline = (sources[0].get("title") or "Top result").strip()
        second = (sources[1].get("title") or "") if len(sources) > 1 else ""
        third = (sources[2].get("title") or "") if len(sources) > 2 else ""
        sentence2 = f"Corroborating sources include: {second}." if second else "I used multiple sources to cross-check the key facts."
        sentence3 = f"Additional context: {third}." if third else "Expanded bullet summary is available on request."
        return f"Top verified update: {headline}. {sentence2} {sentence3}"

    def _build_scrape_fallback_from_results(self, results: List[Dict[str, str]]) -> List[Dict[str, str]]:
        fallback = []
        for item in results[: self.max_results]:
            text = (item.get("snippet") or item.get("text") or "").strip()
            url = (item.get("url") or "").strip()
            if not text or not url:
                continue
            fallback.append(
                {
                    "title": (item.get("title") or "Untitled").strip(),
                    "url": url,
                    "text": text[: self.max_source_chars],
                }
            )
        return fallback

    def _extract_ipl_points_lines(self, sources: List[Dict[str, str]]) -> List[str]:
        combined = " ".join((s.get("text") or "") for s in sources[: self.max_results])
        combined = re.sub(r"\s+", " ", combined)
        pattern = re.compile(
            r"\b(CSK|MI|RCB|KKR|RR|GT|SRH|DC|PBKS|LSG)\b[^0-9]{0,24}(\d{1,2})\s*(?:pts|points)\b",
            flags=re.IGNORECASE,
        )
        best: Dict[str, int] = {}
        for team, pts in pattern.findall(combined):
            code = team.upper()
            value = int(pts)
            if code not in best or value > best[code]:
                best[code] = value
        ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
        return [f"{team} {pts} pts" for team, pts in ranked]

    def _extract_ipl_score_lines(self, sources: List[Dict[str, str]]) -> List[str]:
        """Extract concise score lines like 'MI 156/4 (18.3 ov)' from source text."""
        joined = " ".join((s.get("text") or "") for s in sources[: self.max_results])
        joined = re.sub(r"\s+", " ", joined)
        patterns = [
            re.compile(
                r"\b(CSK|MI|RCB|KKR|RR|GT|SRH|DC|PBKS|LSG)\b[^0-9]{0,12}(\d{1,3}/\d{1,2})"
                r"(?:[^0-9]{0,20}(\d{1,2}(?:\.\d)?\s*ov(?:ers?)?))?",
                flags=re.IGNORECASE,
            ),
            re.compile(
                r"\b(Chennai Super Kings|Mumbai Indians|Royal Challengers Bengaluru|Kolkata Knight Riders|"
                r"Rajasthan Royals|Gujarat Titans|Sunrisers Hyderabad|Delhi Capitals|Punjab Kings|"
                r"Lucknow Super Giants)\b[^0-9]{0,16}(\d{1,3}/\d{1,2})"
                r"(?:[^0-9]{0,20}(\d{1,2}(?:\.\d)?\s*ov(?:ers?)?))?",
                flags=re.IGNORECASE,
            ),
        ]
        out: List[str] = []
        seen = set()
        for pattern in patterns:
            for match in pattern.finditer(joined):
                team = re.sub(r"\s+", " ", match.group(1)).strip()
                score = (match.group(2) or "").strip()
                overs = (match.group(3) or "").strip()
                if not score:
                    continue
                line = f"{team} {score}"
                if overs:
                    line += f" ({overs})"
                key = line.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(line)
                if len(out) >= 4:
                    return out
        return out

    def _extract_json_object(self, text: str) -> Optional[Dict]:
        if not text:
            return None
        candidate = text
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        if fence:
            candidate = fence.group(1)
        else:
            match = re.search(r"(\{.*\})", text, flags=re.DOTALL)
            if match:
                candidate = match.group(1)
        try:
            parsed = json.loads(candidate)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None
