# Searching Skill

Source: `calcie_core/skills/searching.py`

## Purpose
Handle web-search intents, gather multi-source content, and return contradiction-aware synthesis.

## Class
`SearchingSkill(llm_collect_text, fallback_search=None, max_results=5, max_source_chars=5000)`

## Intent handling
`is_search_intent` catches:
- explicit commands: `search`, `web search`, `lookup`, `find`
- news phrases: `latest ... news`, `headlines`
- live/sports phrases: `who won last night ipl`, `ipl points table`, `standings`

Input cleanup also strips transcript noise (`intent=...`, `reason=...`, trailing console fragments).

## Provider cascade
Default order (`auto`):
1. Tavily
2. Exa
3. DDGS

If Tavily/Exa hit quota/rate limits, cascade continues automatically.

## Search pipeline
1. Detect intent and extract cleaned query.
2. Fetch results from provider chain.
3. Build source texts (provider content -> URL scrape -> snippet fallback).
4. Synthesize into exactly 3 concise factual sentences.
5. If synthesis is low quality (placeholder/meta text), use deterministic fallback summary.

## Public entry point
- `handle_query(user_input) -> (response_text|None, speech_text|None)`

Returns:
- `(None, None)` when not a search query
- response text with:
  - 3-sentence summary
  - provider used
  - provider attempts
  - source list

## Environment variables
Required (at least one):
- `TAVILY_API_KEY`
- `EXA_API_KEY`

Optional:
- `CALCIE_SEARCH_PROVIDER=auto|tavily|exa|ddgs` (default: `auto`)
- `CALCIE_RESEARCH_TIMEOUT_S=24`
- `CALCIE_RESEARCH_POLL_S=1.0`
- `CALCIE_DDGS_FALLBACK_RESULTS=5`
- `CALCIE_SEARCH_ALLOW_FALLBACK=0|1` (legacy fallback path)

## Quota/failure handling
Recognizes common quota/rate-limit signals:
- `429`, `quota`, `rate limit`, `insufficient credits`, `out of tokens`

If all providers fail, returns a concise attempts trace (for debugging).
