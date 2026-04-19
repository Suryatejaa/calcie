# CALCIE Skills

This directory contains task-specific skills used by `calcie.py`.

## Current skills
- `app_access.py`: deterministic app command parsing and app launching.
- `agentic_computer_use.py`: essential-task multi-step planner that cross-uses app/search/computer skills.
- `coding.py`: codebase read/search/explain + guarded proposal/apply workflow.
- `computer_control.py`: local desktop controls (screenshot/click/scroll/type/keys) with arm-lock safety.
- `screen_vision.py`: continuous screen monitoring loop with multimodal vision analysis and alerts.
- `searching.py`: provider-backed web search (Tavily/Exa), page scraping, and LLM synthesis.

Detailed docs:
- [App Access Skill](./docs/app_access.md)
- [Agentic Computer Use Skill](./docs/agentic_computer_use.md)
- [Coding Skill](./docs/coding.md)
- [Computer Control Skill](./docs/computer_control.md)
- [Screen Vision Skill](./docs/screen_vision.md)
- [Searching Skill](./docs/searching.md)

## Skill contract
Each skill should expose:
- intent detection (`is_*` or `handle_*` entry point)
- deterministic handling for supported commands
- a tuple response shape for chat routing: `(text_response, speech_response)` or `(None, None)` when not handled

## Global LLM selector
Runtime provider can be forced from `.env`:
- `CALCIE_LLM_PROVIDER=auto|gemini|openai|claude|grok|ollama`

Notes:
- `auto`: provider auto-selection + fallback chain.
- any explicit provider: strict mode (no automatic provider switching).
- alias supported for compatibility: `CALCIE_LLM_MODE` (same values).

## Search provider env
Set at least one key:
- `TAVILY_API_KEY`
- `EXA_API_KEY`

Search cascade (default): `tavily -> exa -> ddgs`.
If Tavily quota/rate limit is exhausted, it falls through to Exa.
If Exa also fails or quota is exhausted, it falls through to DDGS URL retrieval + page extraction + LLM synthesis.

Optional tuning:
- `CALCIE_SEARCH_PROVIDER=auto|tavily|exa` (default: `auto`)
- `CALCIE_RESEARCH_TIMEOUT_S=24` (Tavily research polling timeout)
- `CALCIE_RESEARCH_POLL_S=1.0` (poll interval)
- `CALCIE_DDGS_FALLBACK_RESULTS=5` (DDGS URLs to fetch when both providers fail)
- `CALCIE_SEARCH_ALLOW_FALLBACK=0|1` (default `0`; legacy fallback search)
