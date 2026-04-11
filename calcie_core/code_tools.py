"""Codebase tooling for Calcie Phase B (guarded sandbox proposals + apply)."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


@dataclass
class CodeSearchHit:
    path: str
    line: int
    text: str


@dataclass
class CodeProposal:
    proposal_id: str
    target_rel: str
    sandbox_rel: str
    source_hash: str
    instruction: str
    status: str
    created_at: str
    applied_at: str = ""
    discarded_at: str = ""
    backup_rel: str = ""


class ReadOnlyCodeTools:
    """Filesystem tooling with hard safety constraints and guarded apply workflow."""

    CODE_EXTENSIONS = {
        ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".cpp", ".c",
        ".h", ".hpp", ".cs", ".php", ".rb", ".swift", ".kt", ".kts", ".scala",
        ".sql", ".html", ".css", ".scss", ".md", ".toml", ".yaml", ".yml", ".json",
        ".sh", ".bash", ".zsh",
    }
    IGNORED_DIR_NAMES = {
        ".git", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
        "node_modules", ".venv", "venv", ".idea", ".vscode", ".calcie",
    }
    BLOCKED_READ_NAMES = {".env", ".env.local", ".env.development", ".env.production"}
    BLOCKED_WRITE_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12"}
    BLOCKED_WRITE_DIRS = {".git", ".calcie", "node_modules", ".venv", "venv", "__pycache__"}
    PROPOSALS_FILE = "proposals.json"
    CODE_QUERY_MARKERS = {
        "code", "codebase", "function", "method", "module", "bug", "traceback",
        "stack trace", "endpoint", "import", "refactor", "syntax", "compile",
        "repository", "repo", "source", "debug", "exception", "error",
    }
    STOP_WORDS = {
        "the", "a", "an", "and", "or", "to", "for", "in", "on", "with", "from",
        "about", "this", "that", "please", "could", "would", "should", "can",
        "you", "me", "my", "our", "your", "is", "are", "be", "it", "of", "at",
        "what", "why", "how", "where", "when", "which", "show", "explain", "find",
    }

    def __init__(self, project_root: Path, max_file_chars: int = 30000):
        self.project_root = project_root.resolve()
        self.max_file_chars = max(4000, int(max_file_chars))
        self.calcie_dir = self.project_root / ".calcie"
        self.sandbox_dir = self.calcie_dir / "sandbox"
        self.backups_dir = self.calcie_dir / "backups"
        self.proposals_path = self.calcie_dir / self.PROPOSALS_FILE

    def resolve_relative_path(self, raw_path: str) -> Optional[str]:
        resolved = self._resolve_path(raw_path)
        if not resolved:
            return None
        return resolved.relative_to(self.project_root).as_posix()

    def is_code_query(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        if any(marker in lowered for marker in self.CODE_QUERY_MARKERS):
            return True
        if re.search(r"\b[\w\-/]+\.(py|js|ts|tsx|jsx|java|go|rs|cpp|c|h|md|json|yaml|yml|toml|sql|sh)\b", lowered):
            return True
        if re.search(r"\b(list files|show files|project structure|directory tree|read file|open file)\b", lowered):
            return True
        return False

    def classify_action(self, text: str) -> str:
        lowered = (text or "").lower().strip()
        if any(k in lowered for k in ["directory tree", "project structure", "repo structure", "folder structure"]):
            return "tree"
        if any(k in lowered for k in ["list files", "show files", "what files", "which files"]):
            return "list"
        if any(k in lowered for k in ["read file", "open file", "show file", "cat file", "print file"]):
            return "read"
        if any(k in lowered for k in ["find ", "search ", "where is", "grep ", "look for"]):
            return "search"
        if re.search(r"\bexplain\b", lowered) and ("code" in lowered or "file" in lowered or "function" in lowered):
            return "explain"
        return "explain"

    def list_files(self, directory: str = ".", max_files: int = 240) -> List[str]:
        root = self._resolve_path(directory)
        if root is None or not root.exists() or not root.is_dir():
            return []

        files: List[str] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if self._is_ignored_path(path):
                continue
            rel = path.relative_to(self.project_root).as_posix()
            files.append(rel)
            if len(files) >= max_files:
                break
        return files

    def summarize_tree(self, max_depth: int = 3, max_entries: int = 120) -> str:
        lines: List[str] = []
        entries = 0
        root_depth = len(self.project_root.parts)

        for path in sorted(self.project_root.rglob("*")):
            if entries >= max_entries:
                lines.append("... (truncated)")
                break
            if self._is_ignored_path(path):
                continue
            depth = len(path.parts) - root_depth
            if depth > max_depth:
                continue

            rel = path.relative_to(self.project_root).as_posix()
            indent = "  " * max(0, depth - 1)
            name = rel.split("/")[-1]
            marker = "/" if path.is_dir() else ""
            if path.is_file() and not self._is_probably_code_or_text(path):
                continue
            lines.append(f"{indent}{name}{marker}")
            entries += 1

        return "\n".join(lines) if lines else "(No readable files found)"

    def extract_path(self, text: str) -> Optional[str]:
        if not text:
            return None

        # First: inline code paths like `src/app.py`
        backtick = re.findall(r"`([^`]+)`", text)
        for candidate in backtick:
            if self._resolve_path(candidate):
                return candidate.strip()

        # Then: quoted paths.
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", text)
        for candidate in quoted:
            if self._resolve_path(candidate):
                return candidate.strip()

        # Finally: tokenized path-like fragments.
        tokens = re.split(r"\s+", text.strip())
        for tok in tokens:
            cleaned = tok.strip(".,:;()[]{}<>")
            if "/" not in cleaned and "." not in cleaned:
                continue
            if self._resolve_path(cleaned):
                return cleaned
        return None

    def read_file(
        self,
        path: str,
        start_line: int = 1,
        end_line: int = 220,
        include_line_numbers: bool = True,
    ) -> Tuple[bool, str]:
        resolved = self._resolve_path(path)
        if resolved is None:
            return False, "Path is outside the project or invalid."
        if not resolved.is_file():
            return False, "Path is not a readable file."
        if resolved.name in self.BLOCKED_READ_NAMES:
            return False, "Blocked by safety policy (sensitive file)."
        if self._is_ignored_path(resolved):
            return False, "Blocked by safety policy (ignored path)."

        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return False, f"Could not read file: {exc}"

        lines = text.splitlines()
        total = len(lines)
        start = max(1, int(start_line))
        end = max(start, min(int(end_line), total if total else 1))
        window = lines[start - 1 : end]
        if include_line_numbers:
            rendered = "\n".join(f"{idx:>4} | {line}" for idx, line in enumerate(window, start=start))
        else:
            rendered = "\n".join(window)

        if len(rendered) > self.max_file_chars:
            rendered = rendered[: self.max_file_chars].rstrip() + "\n... (truncated)"

        rel = resolved.relative_to(self.project_root).as_posix()
        header = f"File: {rel} (lines {start}-{end} of {total})"
        return True, f"{header}\n{rendered}"

    def read_source(self, path: str) -> Tuple[bool, str, str]:
        resolved = self._resolve_path(path)
        if resolved is None:
            return False, "", "Path is outside the project or invalid."
        if not resolved.is_file():
            return False, "", "Path is not a readable file."
        if resolved.name in self.BLOCKED_READ_NAMES:
            return False, "", "Blocked by safety policy (sensitive file)."
        if self._is_ignored_path(resolved):
            return False, "", "Blocked by safety policy (ignored path)."

        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return False, "", f"Could not read file: {exc}"

        if len(text) > self.max_file_chars:
            text = text[: self.max_file_chars]

        rel = resolved.relative_to(self.project_root).as_posix()
        return True, rel, text

    def extract_search_term(self, text: str) -> Optional[str]:
        if not text:
            return None
        for pattern in [
            r"\bfind\s+(.+)$",
            r"\bsearch\s+for\s+(.+)$",
            r"\bsearch\s+(.+)$",
            r"\bwhere\s+is\s+(.+)$",
            r"\blook\s+for\s+(.+)$",
        ]:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                term = match.group(1).strip().strip("?.!,")
                if term:
                    return term
        return None

    def search_code(self, pattern: str, max_results: int = 24) -> List[CodeSearchHit]:
        if not pattern:
            return []
        query = pattern.strip()
        if not query:
            return []

        lowered_query = query.lower()
        is_regex = any(ch in query for ch in "^$.*+?[](){}|\\")
        hits: List[CodeSearchHit] = []

        for file_path in self._iter_code_files():
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not text:
                continue

            lines = text.splitlines()
            for line_no, line in enumerate(lines, start=1):
                matched = False
                if is_regex:
                    try:
                        matched = re.search(query, line, flags=re.IGNORECASE) is not None
                    except re.error:
                        matched = lowered_query in line.lower()
                else:
                    matched = lowered_query in line.lower()

                if not matched:
                    continue

                rel = file_path.relative_to(self.project_root).as_posix()
                snippet = line.strip()
                if len(snippet) > 180:
                    snippet = snippet[:180].rstrip() + "..."
                hits.append(CodeSearchHit(path=rel, line=line_no, text=snippet))
                if len(hits) >= max_results:
                    return hits
        return hits

    def show_diff(
        self,
        original: str,
        updated: str,
        from_name: str = "original",
        to_name: str = "updated",
    ) -> str:
        diff_lines = difflib.unified_diff(
            original.splitlines(),
            updated.splitlines(),
            fromfile=from_name,
            tofile=to_name,
            lineterm="",
        )
        rendered = "\n".join(diff_lines)
        if not rendered:
            return "(No diff)"
        if len(rendered) > self.max_file_chars:
            return rendered[: self.max_file_chars].rstrip() + "\n... (truncated)"
        return rendered

    def write_file(self, path: str, content: str) -> str:
        _ = (path, content)
        return "Direct write blocked: use `code propose ...` then `code apply ...`."

    def create_proposal(
        self,
        target_path: str,
        new_content: str,
        instruction: str,
        max_diff_chars: int = 14000,
    ) -> Tuple[bool, str]:
        resolved = self._resolve_path(target_path)
        if resolved is None:
            return False, "Proposal failed: target path is outside project root."
        if not resolved.exists() or not resolved.is_file():
            return False, "Proposal failed: target path is not an existing file."
        if self._is_write_blocked(resolved):
            return False, "Proposal failed: write blocked for this target path."

        try:
            original = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return False, f"Proposal failed: could not read target file ({exc})."

        updated = (new_content or "").replace("\r\n", "\n")
        if updated == original:
            return False, "Proposal skipped: generated content has no changes."

        target_rel = resolved.relative_to(self.project_root).as_posix()
        proposal_id = self._new_proposal_id(target_rel, instruction)
        sandbox_file = self.sandbox_dir / target_rel
        sandbox_file.parent.mkdir(parents=True, exist_ok=True)
        sandbox_file.write_text(updated, encoding="utf-8")

        diff = self.show_diff(
            original,
            updated,
            from_name=target_rel,
            to_name=(Path(".calcie") / "sandbox" / target_rel).as_posix(),
        )
        if len(diff) > max_diff_chars:
            diff = diff[:max_diff_chars].rstrip() + "\n... (diff truncated)"

        source_hash = self._sha256_text(original)
        created_at = self._now_iso()
        proposal = CodeProposal(
            proposal_id=proposal_id,
            target_rel=target_rel,
            sandbox_rel=sandbox_file.relative_to(self.project_root).as_posix(),
            source_hash=source_hash,
            instruction=instruction.strip(),
            status="pending",
            created_at=created_at,
        )

        proposals = self._load_proposals()
        proposals.append(proposal.__dict__)
        self._save_proposals(proposals)

        preview = (
            f"Proposal created: {proposal_id}\n"
            f"Target: {target_rel}\n"
            f"Sandbox: {proposal.sandbox_rel}\n"
            f"Status: pending\n\n"
            f"Diff preview:\n{diff}\n\n"
            f"Apply with: code apply {proposal_id}\n"
            f"Discard with: code discard {proposal_id}"
        )
        return True, preview

    def list_proposals(self, status_filter: Optional[str] = None) -> List[CodeProposal]:
        proposals = [CodeProposal(**p) for p in self._load_proposals()]
        if status_filter:
            proposals = [p for p in proposals if p.status == status_filter]
        proposals.sort(key=lambda p: p.created_at, reverse=True)
        return proposals

    def get_proposal_diff(self, proposal_id: str, max_diff_chars: int = 14000) -> Tuple[bool, str]:
        proposal = self._find_proposal(proposal_id)
        if proposal is None:
            return False, f"No proposal found for id '{proposal_id}'."

        target = self.project_root / proposal.target_rel
        sandbox = self.project_root / proposal.sandbox_rel
        if not target.exists() or not target.is_file():
            return False, f"Target file missing for proposal '{proposal_id}'."
        if not sandbox.exists() or not sandbox.is_file():
            return False, f"Sandbox file missing for proposal '{proposal_id}'."

        original = target.read_text(encoding="utf-8", errors="replace")
        updated = sandbox.read_text(encoding="utf-8", errors="replace")
        diff = self.show_diff(original, updated, from_name=proposal.target_rel, to_name=proposal.sandbox_rel)
        if len(diff) > max_diff_chars:
            diff = diff[:max_diff_chars].rstrip() + "\n... (diff truncated)"

        status_line = f"Proposal {proposal_id} [{proposal.status}]"
        return True, f"{status_line}\n\n{diff}"

    def apply_proposal(self, proposal_id: str) -> Tuple[bool, str]:
        proposals = self._load_proposals()
        idx = self._find_proposal_index(proposals, proposal_id)
        if idx < 0:
            return False, f"No proposal found for id '{proposal_id}'."

        proposal = CodeProposal(**proposals[idx])
        if proposal.status != "pending":
            return False, f"Proposal '{proposal_id}' is not pending (status: {proposal.status})."

        target = self.project_root / proposal.target_rel
        sandbox = self.project_root / proposal.sandbox_rel
        if not target.exists() or not target.is_file():
            return False, f"Apply failed: target file missing ({proposal.target_rel})."
        if not sandbox.exists() or not sandbox.is_file():
            return False, f"Apply failed: sandbox file missing ({proposal.sandbox_rel})."
        if self._is_write_blocked(target):
            return False, "Apply failed: target path blocked by safety policy."

        original = target.read_text(encoding="utf-8", errors="replace")
        current_hash = self._sha256_text(original)
        if current_hash != proposal.source_hash:
            return False, (
                "Apply blocked: target file changed since proposal creation. "
                "Create a new proposal to avoid overwriting working code."
            )

        updated = sandbox.read_text(encoding="utf-8", errors="replace")
        backup = self.backups_dir / proposal_id / proposal.target_rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(original, encoding="utf-8")
        target.write_text(updated, encoding="utf-8")

        proposals[idx]["status"] = "applied"
        proposals[idx]["applied_at"] = self._now_iso()
        proposals[idx]["backup_rel"] = backup.relative_to(self.project_root).as_posix()
        self._save_proposals(proposals)

        return True, (
            f"Applied proposal {proposal_id}.\n"
            f"Updated: {proposal.target_rel}\n"
            f"Backup: {proposals[idx]['backup_rel']}"
        )

    def discard_proposal(self, proposal_id: str) -> Tuple[bool, str]:
        proposals = self._load_proposals()
        idx = self._find_proposal_index(proposals, proposal_id)
        if idx < 0:
            return False, f"No proposal found for id '{proposal_id}'."

        proposal = CodeProposal(**proposals[idx])
        if proposal.status != "pending":
            return False, f"Proposal '{proposal_id}' cannot be discarded (status: {proposal.status})."

        sandbox = self.project_root / proposal.sandbox_rel
        if sandbox.exists() and sandbox.is_file():
            try:
                sandbox.unlink()
            except OSError:
                pass

        proposals[idx]["status"] = "discarded"
        proposals[idx]["discarded_at"] = self._now_iso()
        self._save_proposals(proposals)
        return True, f"Discarded proposal {proposal_id}."

    def build_query_context(
        self,
        query: str,
        max_files: int = 4,
        snippet_lines: int = 100,
    ) -> str:
        lines: List[str] = []
        lines.append(f"Project root: {self.project_root}")

        tree = self.summarize_tree(max_depth=2, max_entries=60)
        lines.append("Project structure:\n" + tree)

        explicit_path = self.extract_path(query)
        selected: List[str] = []
        if explicit_path:
            resolved = self._resolve_path(explicit_path)
            if resolved and resolved.is_file():
                selected.append(resolved.relative_to(self.project_root).as_posix())

        if not selected:
            keywords = self._keywords_from_query(query)
            ranked = self._rank_files_by_keywords(keywords)
            selected.extend(ranked[:max_files])

        if not selected:
            selected.extend(self.list_files(max_files=max_files))

        selected = selected[:max_files]
        for rel in selected:
            ok, content = self.read_file(rel, start_line=1, end_line=snippet_lines)
            if not ok:
                continue
            lines.append(content)

        search_term = self.extract_search_term(query)
        if search_term:
            hits = self.search_code(search_term, max_results=12)
            if hits:
                hit_lines = ["Search hits:"]
                for hit in hits:
                    hit_lines.append(f"- {hit.path}:{hit.line} -> {hit.text}")
                lines.append("\n".join(hit_lines))

        return "\n\n".join(lines)

    def _keywords_from_query(self, query: str) -> List[str]:
        words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", query.lower())
        return [w for w in words if w not in self.STOP_WORDS][:8]

    def _rank_files_by_keywords(self, keywords: Iterable[str]) -> List[str]:
        keys = [k for k in keywords if k]
        if not keys:
            return []

        scored: List[Tuple[int, str]] = []
        for path in self._iter_code_files():
            rel = path.relative_to(self.project_root).as_posix()
            score = 0
            lower_rel = rel.lower()
            for key in keys:
                if key in lower_rel:
                    score += 4

            try:
                preview = path.read_text(encoding="utf-8", errors="replace")[:7000].lower()
            except OSError:
                preview = ""
            for key in keys:
                if key in preview:
                    score += 1
            if score > 0:
                scored.append((score, rel))

        scored.sort(key=lambda item: (-item[0], item[1]))
        return [rel for _, rel in scored]

    def _iter_code_files(self):
        for path in sorted(self.project_root.rglob("*")):
            if not path.is_file():
                continue
            if self._is_ignored_path(path):
                continue
            if path.name in self.BLOCKED_READ_NAMES:
                continue
            if self._is_probably_code_or_text(path):
                yield path

    def _is_probably_code_or_text(self, path: Path) -> bool:
        suffix = path.suffix.lower()
        if suffix in self.CODE_EXTENSIONS:
            return True
        # Extension-less scripts and config files.
        if suffix == "" and path.name.lower() in {"makefile", "dockerfile"}:
            return True

        try:
            with path.open("rb") as fh:
                chunk = fh.read(1024)
        except OSError:
            return False
        if not chunk:
            return True
        if b"\x00" in chunk:
            return False
        return True

    def _resolve_path(self, raw_path: str) -> Optional[Path]:
        if not raw_path:
            return None
        cleaned = raw_path.strip().strip("'\"")
        if not cleaned:
            return None

        candidate = Path(cleaned)
        if not candidate.is_absolute():
            candidate = (self.project_root / candidate).resolve()
        else:
            candidate = candidate.resolve()

        try:
            candidate.relative_to(self.project_root)
        except ValueError:
            return None
        return candidate

    def _is_write_blocked(self, path: Path) -> bool:
        try:
            rel = path.relative_to(self.project_root)
        except ValueError:
            return True

        if path.name in self.BLOCKED_READ_NAMES:
            return True
        if path.suffix.lower() in self.BLOCKED_WRITE_SUFFIXES:
            return True
        if any(part in self.BLOCKED_WRITE_DIRS for part in rel.parts):
            return True
        return False

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _sha256_text(self, text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

    def _new_proposal_id(self, target_rel: str, instruction: str) -> str:
        seed = f"{target_rel}|{instruction}|{self._now_iso()}"
        suffix = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"p{stamp}-{suffix}"

    def _load_proposals(self) -> List[dict]:
        if not self.proposals_path.exists():
            return []
        try:
            raw = self.proposals_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, list):
                return [p for p in data if isinstance(p, dict)]
        except (OSError, json.JSONDecodeError):
            return []
        return []

    def _save_proposals(self, proposals: List[dict]) -> None:
        self.calcie_dir.mkdir(parents=True, exist_ok=True)
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(proposals, indent=2, ensure_ascii=True)
        self.proposals_path.write_text(payload, encoding="utf-8")

    def _find_proposal(self, proposal_id: str) -> Optional[CodeProposal]:
        for item in self._load_proposals():
            if item.get("proposal_id") == proposal_id:
                return CodeProposal(**item)
        return None

    def _find_proposal_index(self, proposals: List[dict], proposal_id: str) -> int:
        for idx, item in enumerate(proposals):
            if item.get("proposal_id") == proposal_id:
                return idx
        return -1

    def _is_ignored_path(self, path: Path) -> bool:
        try:
            rel = path.relative_to(self.project_root)
        except ValueError:
            return True

        parts = rel.parts
        if any(part in self.IGNORED_DIR_NAMES for part in parts):
            return True
        if any(part.startswith(".") and part not in {".", ".."} for part in parts[:-1]):
            return True
        # Skip obvious large artifacts.
        if path.is_file():
            if path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".bin", ".png", ".jpg", ".jpeg", ".gif", ".mp3", ".mp4"}:
                return True
            try:
                if os.path.getsize(path) > 2_000_000:
                    return True
            except OSError:
                return True
        return False
