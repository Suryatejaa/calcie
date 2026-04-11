# Computer Control Skill

Source: `calcie_core/skills/computer_control.py`

## What it is
`ComputerControlSkill` is CALCIE's local desktop action layer.
It supports:
- screenshots
- scrolling
- mouse move/click
- typing and keyboard actions

It is designed with a safety gate so accidental commands do not immediately control your machine.

## How it works (execution flow)
1. User message enters `calcie.py` chat routing.
2. `ComputerControlSkill.handle_command()` checks if text matches a control intent.
3. If not a control intent: returns `(None, None)` and other skills continue.
4. If control intent:
   - validates global enable flag
   - parses command with regex patterns
   - enforces arm-lock for interactive actions (if enabled)
   - executes action via backend
5. Returns `(response_text, speech_text)` back to main chat loop.

Primary backend:
- `pyautogui` for mouse/keyboard/screen APIs.

Screenshot fallback:
- on macOS, `screencapture -x` is used when `pyautogui` is unavailable.

## Command list
- `control help`
- `control status`
- `control cursor` or `control position`
- `control screen size`
- `control arm`
- `control disarm`
- `screenshot [label]`
- `take screenshot [label]`
- `scroll up|down [amount]`
- `click <x> <y>`
- `click at <x> <y>`
- `double click <x> <y>`
- `right click <x> <y>`
- `move <x> <y>` or `move mouse <x> <y>`
- `type <text>`
- `press <key>`
- `hotkey <key1+key2+...>`

## Safety model
Arm-lock:
- controlled by `CALCIE_COMPUTER_REQUIRE_ARM`
- when enabled, actions like `click/type/press/hotkey/scroll/move` are blocked until you run `control arm`
- arm expires after `CALCIE_COMPUTER_ARM_SECONDS`
- `control disarm` immediately disables active window

Dry-run mode:
- controlled by `CALCIE_COMPUTER_DRY_RUN`
- simulates actions and prints what would happen
- useful for testing commands without touching desktop state

Fail-safe:
- `pyautogui.FAILSAFE = True`
- moving cursor rapidly to top-left corner can interrupt automation

## Environment variables
- `CALCIE_COMPUTER_CONTROL_ENABLED=1|0` (default: `1`)
- `CALCIE_COMPUTER_REQUIRE_ARM=1|0` (default: `1`)
- `CALCIE_COMPUTER_ARM_SECONDS=<10..300>` (default: `45`)
- `CALCIE_COMPUTER_DRY_RUN=1|0` (default: `0`)

Recommended local dev setup:
```env
CALCIE_COMPUTER_CONTROL_ENABLED=1
CALCIE_COMPUTER_REQUIRE_ARM=1
CALCIE_COMPUTER_ARM_SECONDS=45
CALCIE_COMPUTER_DRY_RUN=1
```

Then switch `CALCIE_COMPUTER_DRY_RUN=0` when you are ready for real actions.

## macOS permission setup
Required for real desktop control and screenshots.

1. Open `System Settings` -> `Privacy & Security`.
2. Open `Accessibility` and enable the app that runs Python:
   - `Terminal` or `iTerm` or `Visual Studio Code` terminal host.
3. Open `Screen Recording` and enable the same app.
4. Optional: open `Input Monitoring` and enable same app for extra keyboard compatibility.
5. Fully quit and reopen the app after toggling permissions.
6. Re-run CALCIE and test:
   - `control status`
   - `control arm`
   - `take screenshot test`
   - `click at 500 400`

If app is not listed:
- click `+` and add from `/Applications`.

## Usage examples
Basic:
```text
control status
control arm
click at 640 420
type hello world
press enter
control disarm
```

Screenshot workflow:
```text
take screenshot login_page
```
Output file:
- `.calcie/computer/screenshot_YYYYMMDD_HHMMSS_login_page.png`

## Troubleshooting
`Computer action backend unavailable`:
- install dependencies:
```bash
pip install pyautogui pillow
```
- restart terminal and rerun.

`Screenshot failed` on macOS:
- verify Screen Recording permission.
- if permission was just enabled, restart terminal app.

`Computer control is locked`:
- run `control arm` and retry within arm window.

Nothing happens on action commands:
- ensure `CALCIE_COMPUTER_CONTROL_ENABLED=1`.
- check `control status` for backend and lock state.

## Scope and limits
Current phase supports coordinate-based interaction and direct key/mouse commands.
It does not yet include:
- OCR-based "click by text"
- semantic UI understanding
- autonomous multi-step browser planning

Those can be layered in next phases on top of this safety-first base.
