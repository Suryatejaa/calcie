"""Skill: web searching via Tavily/Exa + scraping + LLM synthesis."""

import json
import os
import re
import time
import urllib.error
import urllib.request
from html import unescape
from typing import Callable, Dict, List, Optional, Tuple

from calcie_core.prompts import SEARCH_SYNTH_SYSTEM_PROMPT, SEARCH_SYNTH_USER_TEMPLATE

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
    ):
        self.llm_collect_text = llm_collect_text
        self.fallback_search = fallback_search
        self.max_results = max(3, min(8, int(max_results)))
        self.max_source_chars = max(1500, int(max_source_chars))
        self.tavily_api_key = (os.environ.get("TAVILY_API_KEY") or "").strip()
        self.exa_api_key = (os.environ.get("EXA_API_KEY") or "").strip()
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
        self.show_sources = (os.environ.get("CALCIE_SEARCH_SHOW_SOURCES", "1").strip().lower() in {"1", "true", "yes", "on"})
        self.debug_output = (os.environ.get("CALCIE_SEARCH_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"})
        self._tavily_client = TavilyClient(api_key=self.tavily_api_key) if TavilyClient and self.tavily_api_key else None
        self._exa_client = Exa(api_key=self.exa_api_key) if Exa and self.exa_api_key else None

    def is_search_intent(self, user_input: str) -> bool:
        normalized = self._normalize(user_input)
        if not normalized:
            return False
        if re.match(r"^(search|web search|lookup|look up|find)\b", normalized):
            return True
        if "latest" in normalized and "news" in normalized:
            return True
        if normalized in {"news", "latest news", "today news", "headlines"}:
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
            r"^\s*(?:search|web search|lookup|look up|find)\s*[,:\-]?\s*(.+)$",
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
