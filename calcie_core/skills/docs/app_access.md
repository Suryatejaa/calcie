# App Access Skill

Source: `calcie_core/skills/app_access.py`

## Purpose
Handle app-opening requests deterministically, without LLM routing.

## Class
`AppAccessSkill(app_aliases: Dict[str, str])`

## Public methods
- `extract_open_app_command(user_input: str) -> Optional[str]`
- `looks_like_open_app_intent(user_input: str) -> bool`
- `open_app(app_name: str) -> str`
- `open_target_in_app(target: str, app_name: str) -> str`
- `handle_command(user_input: str) -> Tuple[Optional[str], Optional[str]]`

## Input patterns
Recognized forms include:
- direct alias: `chrome`, `vscode`, `terminal`
- imperative: `open chrome`, `launch the terminal`, `please open spotify`
- polite imperative: `can you open chrome`, `could you launch safari`
- target-in-app: `open amazon in chrome`, `open youtube in safari`, `open github.com in firefox`
- play-routing:
  - `play music` -> opens YouTube Music and attempts resume
  - `play <song name>` -> searches on YouTube Music (default)
  - `play video song <name>` -> prefers direct playable YouTube video URL
  - `play <song> on youtube` / `play <song> on yt music`

If only intent is present (`open`, `open a`), it returns a prompt asking for app name.

## Output contract
`handle_command` returns:
- `(response_text, speech_text)` when handled
- `(None, None)` when not handled

## Platform behavior
- macOS: `open -a <App Name>`
- Linux: launches `<app_name>` directly
- other platforms: returns not-supported message

macOS note:
- Tries multiple app-name variants automatically (`Voice Memos` and `VoiceMemos`, spaced/non-spaced names).
- For target-in-app commands, uses `open -a <App> <URL>`.
- If the requested browser app is unavailable, URL targets fall back to the system default browser.

## Error behavior
- unknown/invalid app: returns failure message from subprocess exception
- empty app name: asks for valid app name

## Notes
- Alias resolution is supplied by caller (`app_aliases` map).
- Unknown targets with up to 3 words are allowed (`open notion calendar`).
- Non-URL targets in target-in-app mode are converted to:
  - known site aliases (`amazon`, `youtube`, `github`, etc.)
  - or Google search URL fallback.
- Music behavior defaults to YouTube Music (not Apple Music).
- On macOS, media browser routing can reuse existing Chrome/Safari tab (instead of always opening a new window) for better playback continuity.
- Media open behavior defaults to app-first on macOS: try installed YouTube Music/YouTube app, then browser fallback.
- In app mode, CALCIE now tries to reuse the existing YouTube/YouTube Music app window and navigate inside it (Cmd+L + URL) before creating new launches.
- OTT/movie platform flow is deferred for now; current play commands focus on YouTube/YouTube Music.

Optional media env:
- `CALCIE_MEDIA_OPEN_MODE=app_first|browser_only` (default: `app_first`)
- `CALCIE_YOUTUBE_OPEN_MODE=app_only|app_first|browser_only` (optional override)
- `CALCIE_YTMUSIC_OPEN_MODE=app_only|app_first|browser_only` (optional override)
- `CALCIE_YTMUSIC_APP_NAME=<custom app name>`
- `CALCIE_YOUTUBE_APP_NAME=<custom app name>`

macOS discovery:
- In `app_first` mode, CALCIE also scans `/Applications` and `~/Applications` for matching YouTube/YouTube Music app names.
