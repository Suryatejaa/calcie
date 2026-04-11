"""Skill: coding/codebase commands."""

import ast
import re
from typing import Callable, Optional, Tuple

from calcie_core.code_tools import ReadOnlyCodeTools


class CodingSkill:
    def __init__(
        self,
        code_tools: ReadOnlyCodeTools,
        llm_collect_text: Callable[[list, int], str],
        code_max_output_tokens: int,
        code_max_file_chars: int,
    ):
        self.code_tools = code_tools
        self.llm_collect_text = llm_collect_text
        self.code_max_output_tokens = int(code_max_output_tokens)
        self.code_max_file_chars = int(code_max_file_chars)

    def is_code_command(self, user_input: str, code_tools_enabled: bool) -> bool:
        raw = (user_input or "").strip()
        if re.match(r"^\s*code\b", raw, flags=re.IGNORECASE):
            return True
        return bool(code_tools_enabled and self.code_tools.is_code_query(raw))

    def answer_code_with_context(self, user_input: str) -> str:
        context = self.code_tools.build_query_context(
            user_input,
            max_files=4,
            snippet_lines=110,
        )
        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "You are CALCIE in code mode. "
                    "Read-only unless user explicitly requests propose/apply workflow. "
                    "Use provided context only. If missing context, suggest exact next file to inspect."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"User request: {user_input}\n\n"
                    "Project context:\n"
                    f"{context}\n\n"
                    "Answer with:\n"
                    "1) What you found\n"
                    "2) Why it matters\n"
                    "3) Exact next command(s)"
                ),
            },
        ]
        explanation = self.llm_collect_text(
            prompt_messages,
            max_output_tokens=min(self.code_max_output_tokens, 1400),
        )
        if explanation and "model error" not in explanation.lower():
            return explanation

        fallback = context
        max_chars = min(self.code_max_file_chars, 14000)
        if len(fallback) > max_chars:
            fallback = fallback[:max_chars].rstrip() + "\n... (truncated)"
        return (
            "I could not reach a model for a full explanation right now, "
            "but here is the context I gathered:\n\n"
            f"{fallback}"
        )

    def extract_updated_file_payload(self, llm_output: str) -> str:
        text = (llm_output or "").strip()
        if not text:
            return ""

        tagged = re.search(r"<updated_file>\s*(.*?)\s*</updated_file>", text, flags=re.IGNORECASE | re.DOTALL)
        if tagged:
            return tagged.group(1).strip("\n")

        fenced = re.search(r"```(?:[\w.+-]+)?\n(.*?)```", text, flags=re.DOTALL)
        if fenced:
            return fenced.group(1).strip("\n")

        return text

    def build_code_proposal(self, target_path: str, instruction: str) -> Tuple[str, str]:
        ok, rel, source = self.code_tools.read_source(target_path)
        if not ok:
            return f"Proposal failed: {source}", "Proposal failed."

        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "You are a deterministic code transformation engine. "
                    "Apply exactly the requested change to the provided file. "
                    "Preserve unrelated behavior. Return one block as "
                    "<updated_file>...</updated_file> with full file contents."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Target file: {rel}\n"
                    f"Instruction: {instruction}\n\n"
                    "Current file content:\n"
                    f"```text\n{source}\n```"
                ),
            },
        ]
        llm_output = self.llm_collect_text(
            prompt_messages,
            max_output_tokens=min(self.code_max_output_tokens, 2200),
        )
        if not llm_output or "model error" in llm_output.lower():
            return "Proposal failed: model did not return a usable update.", "Proposal failed."

        updated = self.extract_updated_file_payload(llm_output)
        if not updated.strip():
            return "Proposal failed: empty update generated.", "Proposal failed."

        if rel.endswith(".py"):
            try:
                ast.parse(updated)
            except SyntaxError as e:
                return (
                    f"Proposal failed: generated Python is invalid ({e.msg} at line {e.lineno}).",
                    "Proposal failed.",
                )

        created, message = self.code_tools.create_proposal(rel, updated, instruction)
        if not created:
            return message, "Proposal failed."
        return message, "Proposal created."

    def handle_command(self, user_input: str, code_tools_enabled: bool):
        raw = (user_input or "").strip()
        if not self.is_code_command(raw, code_tools_enabled):
            return None, None
        if not code_tools_enabled:
            return (
                "Code tools are disabled. Set CALCIE_CODE_TOOLS_ENABLED=1 to enable code mode.",
                None,
            )

        if re.match(r"^\s*code\s*(help)?\s*$", raw, flags=re.IGNORECASE):
            help_text = (
                "Code mode (Phase B, guarded write):\n"
                "1. code list [path]\n"
                "2. code tree\n"
                "3. code read <file_path>\n"
                "4. code search <pattern>\n"
                "5. code explain <question or path>\n"
                "6. code propose <file_path> :: <change instruction>\n"
                "7. code proposals [pending|applied|discarded|all]\n"
                "8. code diff <proposal_id>\n"
                "9. code apply <proposal_id>\n"
                "10. code discard <proposal_id>\n"
                "Safety: edits go to .calcie/sandbox first; apply is explicit and hash-guarded."
            )
            return help_text, "Code mode ready."

        if re.match(r"^\s*code\s+tree\s*$", raw, flags=re.IGNORECASE):
            tree = self.code_tools.summarize_tree(max_depth=3, max_entries=140)
            return f"Project tree (read-only):\n{tree}", "Showing project tree."

        list_match = re.match(r"^\s*code\s+list(?:\s+(.+))?\s*$", raw, flags=re.IGNORECASE)
        if list_match:
            sub_path = (list_match.group(1) or ".").strip()
            files = self.code_tools.list_files(sub_path, max_files=240)
            if not files:
                return "No readable files found for that path.", "No files found."
            listing = "\n".join(f"- {f}" for f in files)
            return f"Readable files ({len(files)} shown):\n{listing}", "Listed code files."

        read_match = re.match(r"^\s*code\s+read\s+(.+?)\s*$", raw, flags=re.IGNORECASE)
        if read_match:
            arg = read_match.group(1).strip()
            path = self.code_tools.extract_path(arg) or arg
            line_match = re.search(r"\blines?\s+(\d+)\s*(?:-|to|:)\s*(\d+)\b", arg, flags=re.IGNORECASE)
            start_line, end_line = 1, 220
            if line_match:
                start_line = int(line_match.group(1))
                end_line = int(line_match.group(2))
            ok, output = self.code_tools.read_file(path, start_line=start_line, end_line=end_line)
            if not ok:
                return f"Code read failed: {output}", "Code read failed."
            return output, "Read file preview ready."

        search_match = re.match(r"^\s*code\s+search\s+(.+?)\s*$", raw, flags=re.IGNORECASE)
        if search_match:
            pattern = search_match.group(1).strip()
            hits = self.code_tools.search_code(pattern, max_results=30)
            if not hits:
                return f"No matches found for '{pattern}'.", "No matches found."
            lines = [f"Matches for '{pattern}' ({len(hits)}):"]
            lines.extend(f"- {hit.path}:{hit.line} | {hit.text}" for hit in hits)
            return "\n".join(lines), "Search results ready."

        explain_match = re.match(r"^\s*code\s+explain(?:\s+(.+))?\s*$", raw, flags=re.IGNORECASE)
        if explain_match:
            question = (explain_match.group(1) or "").strip()
            if not question:
                question = "Explain the current project architecture."
            return self.answer_code_with_context(question), "Generated explanation."

        propose_match = re.match(
            r"^\s*code\s+propose\s+(.+?)\s*::\s*(.+?)\s*$",
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if propose_match:
            target_path = propose_match.group(1).strip()
            instruction = propose_match.group(2).strip()
            if not target_path or not instruction:
                return (
                    "Usage: code propose <file_path> :: <change instruction>",
                    "Invalid propose command.",
                )
            return self.build_code_proposal(target_path, instruction)
        if re.match(r"^\s*code\s+propose\b", raw, flags=re.IGNORECASE):
            return (
                "Usage: code propose <file_path> :: <change instruction>",
                "Invalid propose command.",
            )

        proposals_match = re.match(
            r"^\s*code\s+proposals(?:\s+(pending|applied|discarded|all))?\s*$",
            raw,
            flags=re.IGNORECASE,
        )
        if proposals_match:
            wanted = (proposals_match.group(1) or "pending").lower()
            status_filter = None if wanted == "all" else wanted
            proposals = self.code_tools.list_proposals(status_filter=status_filter)
            if not proposals:
                return f"No proposals found for filter '{wanted}'.", "No proposals."
            lines = [f"Proposals ({wanted}):"]
            for p in proposals[:30]:
                lines.append(f"- {p.proposal_id} | {p.status} | {p.target_rel} | created {p.created_at}")
            if len(proposals) > 30:
                lines.append(f"...and {len(proposals) - 30} more.")
            return "\n".join(lines), "Listed proposals."

        diff_match = re.match(r"^\s*code\s+diff\s+([A-Za-z0-9\-_.]+)\s*$", raw, flags=re.IGNORECASE)
        if diff_match:
            proposal_id = diff_match.group(1).strip()
            ok, diff_text = self.code_tools.get_proposal_diff(proposal_id)
            if not ok:
                return diff_text, "Diff failed."
            return diff_text, "Showing proposal diff."
        if re.match(r"^\s*code\s+diff\b", raw, flags=re.IGNORECASE):
            return "Usage: code diff <proposal_id>", "Invalid diff command."

        apply_match = re.match(r"^\s*code\s+apply\s+([A-Za-z0-9\-_.]+)\s*$", raw, flags=re.IGNORECASE)
        if apply_match:
            proposal_id = apply_match.group(1).strip()
            ok, msg = self.code_tools.apply_proposal(proposal_id)
            if not ok:
                return msg, "Apply failed."
            return msg, "Proposal applied."
        if re.match(r"^\s*code\s+apply\b", raw, flags=re.IGNORECASE):
            return "Usage: code apply <proposal_id>", "Invalid apply command."

        discard_match = re.match(r"^\s*code\s+discard\s+([A-Za-z0-9\-_.]+)\s*$", raw, flags=re.IGNORECASE)
        if discard_match:
            proposal_id = discard_match.group(1).strip()
            ok, msg = self.code_tools.discard_proposal(proposal_id)
            if not ok:
                return msg, "Discard failed."
            return msg, "Proposal discarded."
        if re.match(r"^\s*code\s+discard\b", raw, flags=re.IGNORECASE):
            return "Usage: code discard <proposal_id>", "Invalid discard command."

        return self.answer_code_with_context(raw), "Generated code analysis."

