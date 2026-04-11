# Agentic Computer Use Skill

Source: `calcie_core/skills/agentic_computer_use.py`

## Purpose
Provide intelligent multi-step orchestration across existing skills for essential real-world tasks.

This skill is not a raw click bot. It plans and executes cross-tool steps such as:
- app opening/navigation
- web search
- computer-control commands
- short guidance output

## Why this exists
CALCIE already had command-specific skills (`play`, `search`, `code`, `control`).
This layer adds a higher-level planner so CALCIE can combine those tools when needed.

## Activation
The skill triggers on essential-task language, for example:
- order/buy/checkout tasks
- watch/play movie on OTT tasks
- explicit "do this on my screen" style requests

If `CALCIE_AGENTIC_COMPUTER_USE_ESSENTIAL_ONLY=1`, non-essential requests are ignored by this skill.

## Planning model
It asks the selected LLM provider to return strict JSON plan steps using tool primitives:
- `app.open_app`
- `app.open_target_in_app`
- `app.play`
- `search.query`
- `computer.command`
- `say`

Provider for planning can be forced independently via env:
- `CALCIE_COMPUTER_USE_PROVIDER=auto|openai|gemini|claude`

## Safety behavior
- max step cap (`CALCIE_COMPUTER_USE_MAX_STEPS`)
- optional auto-arm for computer commands (`CALCIE_COMPUTER_USE_AUTO_ARM`)
- optional confirmation gate before execution (`CALCIE_COMPUTER_USE_REQUIRE_CONFIRM`)
- payment/order finalization is intentionally blocked in planner instructions
- shopping flows stop before final payment
- planner output is sanitized before execution (invalid tool choices are rewritten/dropped)
- execution halts early after repeated failed steps

## Environment variables
- `CALCIE_AGENTIC_COMPUTER_USE_ENABLED=1|0` (default: `1`)
- `CALCIE_AGENTIC_COMPUTER_USE_ESSENTIAL_ONLY=1|0` (default: `1`)
- `CALCIE_COMPUTER_USE_PROVIDER=auto|openai|gemini|claude` (default: `auto`)
- `CALCIE_COMPUTER_USE_MAX_STEPS=2..12` (default: `6`)
- `CALCIE_COMPUTER_USE_AUTO_ARM=1|0` (default: `1`)
- `CALCIE_COMPUTER_USE_REQUIRE_CONFIRM=1|0` (default: `1`)

## Output
Returns an execution trace with per-step status and a safety note for payment-like requests.

When confirmation mode is enabled:
- first response is a plan preview
- user must reply `confirm` to execute
- user can reply `cancel` to discard pending plan
