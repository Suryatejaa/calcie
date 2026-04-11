# Coding Skill

Source: `calcie_core/skills/coding.py`

## Purpose
Provide read/explain/search operations over the repository plus guarded write proposals.

## Class
`CodingSkill(code_tools, llm_collect_text, code_max_output_tokens, code_max_file_chars)`

`code_tools` uses `ReadOnlyCodeTools` from `calcie_core/code_tools.py`.

## Entry points
- `is_code_command(user_input, code_tools_enabled) -> bool`
- `handle_command(user_input, code_tools_enabled) -> (text|None, speech|None)`

## Command surface
- `code help`
- `code tree`
- `code list [path]`
- `code read <file_path>`
- `code read <file_path> lines <start>-<end>`
- `code search <pattern>`
- `code explain <question>`
- `code propose <file_path> :: <change instruction>`
- `code proposals [pending|applied|discarded|all]`
- `code diff <proposal_id>`
- `code apply <proposal_id>`
- `code discard <proposal_id>`

## Proposal workflow (guarded writes)
1. Read source file.
2. Ask LLM to return full updated file in `<updated_file>...</updated_file>`.
3. Validate generated Python with `ast.parse` (for `.py` files).
4. Store proposal in `.calcie/sandbox` via code tools.
5. User explicitly applies/discards by proposal id.

## Output contract
`handle_command` returns:
- `(response_text, speech_text)` when handled
- `(None, None)` when not code-related

## Required config
- `CALCIE_CODE_TOOLS_ENABLED=1` to enable command handling.

## Failure behavior
- Disabled tools: explicit instruction to enable.
- Invalid command shapes: returns usage format.
- LLM failure: deterministic fallback with gathered context.
- Invalid generated Python: proposal rejected with syntax line details.
