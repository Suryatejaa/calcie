# Screen Vision Skill

Source: `calcie_core/skills/screen_vision.py`

## Purpose

Runs a background screen-monitor loop for CALCIE:
- captures screenshots at intervals
- sends them to a multimodal model for analysis
- raises alerts when the monitoring goal is matched
- can optionally trigger safe local commands

## Commands

- `vision help`
- `vision status`
- `vision start <goal>`
- `vision once <goal>`
- `vision stop`
- `vision events`
- `vision interval <seconds>`

Examples:

```text
vision start watch for red production errors in the terminal
vision once check whether this dashboard shows a severe outage
vision stop
```

## Defaults

- alert-only by default
- desktop notification + spoken alert on macOS
- actions are disabled unless explicitly enabled
- screenshots are stored under `.calcie/vision/captures`
- event history is appended to `.calcie/vision/events.jsonl`

## Environment

```env
CALCIE_SCREEN_VISION_ENABLED=1
CALCIE_SCREEN_VISION_INTERVAL_S=12
CALCIE_SCREEN_VISION_KEEP_ALL_CAPTURES=0
CALCIE_SCREEN_VISION_ALLOW_ACTIONS=0
CALCIE_SCREEN_VISION_MAX_EVENTS=30
CALCIE_SCREEN_VISION_NOTIFY_COOLDOWN_S=45
CALCIE_SCREEN_VISION_DESKTOP_NOTIFY=1

CALCIE_VISION_PROVIDER=auto
CALCIE_VISION_MODEL=gemini-2.5-flash
CALCIE_VISION_OPENAI_MODEL=gpt-4.1-mini
CALCIE_VISION_CLAUDE_MODEL=claude-sonnet-4-20250514
```

## Provider Behavior

- `gemini` is the preferred vision path when configured.
- `auto` tries Gemini, then OpenAI, then Claude.
- analysis returns structured JSON with:
  - `matched`
  - `severity`
  - `summary`
  - `alert_message`
  - `should_act`
  - `action_command`
  - `evidence`

## Safety

- auto-actions are off unless `CALCIE_SCREEN_VISION_ALLOW_ACTIONS=1`
- only safe local command prefixes are allowed for auto-action:
  - `control`
  - `computer`
  - `open`
  - `play`
  - `search`
- unsafe action strings are blocked

## Notes

- this is continuous monitoring, not a hidden OS-level watcher
- on macOS you still need Screen Recording permission for screenshot capture
- if `pyautogui` is unavailable on macOS, CALCIE falls back to `screencapture`
