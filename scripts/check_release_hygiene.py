#!/usr/bin/env python3
"""Fail release/CI if private CALCIE data or obvious secrets are about to ship."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BANNED_PATH_PARTS = {
    ".calcie",
    "screen_memory",
    "profile_imports",
    "captures",
    "ocr",
    "chroma",
    "__pycache__",
}

BANNED_FILE_NAMES = {
    ".env",
    ".env.local",
    "calcie_profile.local.json",
    "context.local.json",
    "chatgpt_memory_export.md",
    "calcie_history.db",
    "calcie_facts.json",
    "sync_server.db",
}

SECRET_ASSIGNMENT_RE = re.compile(
    r"(?m)^[ \t]*([A-Z][A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|PRIVATE_KEY|CLIENT_SECRET|ACCESS_KEY)[A-Z0-9_]*)=([^\s#]*)"
)

LONG_SECRET_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_-]{20,}|apify_api_[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{20,}|ghp_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{40,}|xox[baprs]-[A-Za-z0-9-]{20,}|AKIA[0-9A-Z]{16})(?![A-Za-z0-9])"
)

ALLOW_VALUE_MARKERS = {
    "",
    "placeholder",
    "changeme",
    "change_me",
    "your_key_here",
    "your-api-key",
    "your_api_key",
    "your_token",
    "YOUR_API_KEY",
    "YOUR_TOKEN",
    "YOUR_SERVER_IP:8000",
}

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".build",
    ".swiftpm",
    ".expo",
    "DerivedData",
}

SCAN_ARTIFACT_DIRS = ["dist", "release", "releases", "build"]
TEXT_EXTENSIONS = {
    ".json",
    ".md",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".swift",
    ".plist",
    ".yml",
    ".yaml",
    ".sh",
    ".txt",
    ".env",
    ".example",
    ".html",
    ".css",
}


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def is_text_candidate(path: Path) -> bool:
    if path.name in {".env", ".env.example"}:
        return True
    return path.suffix.lower() in TEXT_EXTENSIONS


def tracked_files() -> list[Path]:
    try:
        output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    except Exception:
        return []
    files = []
    for raw in output.split(b"\0"):
        if raw:
            files.append(ROOT / raw.decode("utf-8", errors="replace"))
    return files


def artifact_files() -> list[Path]:
    found: list[Path] = []
    for dirname in SCAN_ARTIFACT_DIRS:
        base = ROOT / dirname
        if not base.exists():
            continue
        for current_root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for filename in files:
                found.append(Path(current_root) / filename)
    return found


def explicit_arg_files(args: list[str]) -> list[Path]:
    found: list[Path] = []
    for arg in args:
        path = (ROOT / arg).resolve() if not os.path.isabs(arg) else Path(arg).resolve()
        if not path.exists():
            continue
        if path.is_file():
            found.append(path)
            continue
        for current_root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for filename in files:
                found.append(Path(current_root) / filename)
    return found


def path_issues(path: Path) -> list[str]:
    issues: list[str] = []
    parts = set(path.relative_to(ROOT).parts)
    if path.name in BANNED_FILE_NAMES:
        issues.append(f"banned private file name: {path.name}")
    for part in sorted(parts & BANNED_PATH_PARTS):
        issues.append(f"banned private path segment: {part}")
    return issues


def value_is_placeholder(value: str) -> bool:
    cleaned = value.strip().strip('"\'')
    if cleaned in ALLOW_VALUE_MARKERS:
        return True
    lowered = cleaned.lower()
    return (
        "your" in lowered
        or "example" in lowered
        or "placeholder" in lowered
        or lowered.startswith("<")
    )


def content_issues(path: Path) -> list[str]:
    if not is_text_candidate(path):
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    issues: list[str] = []
    rel_path = rel(path)
    is_example = rel_path.endswith(".env.example") or ".example" in path.name

    for key, value in SECRET_ASSIGNMENT_RE.findall(text):
        if not is_example and not value_is_placeholder(value):
            issues.append(f"possible secret assignment: {key}")

    if not is_example:
        if LONG_SECRET_RE.search(text):
            issues.append("possible long secret token")

    return issues


def main() -> int:
    targets = tracked_files()
    targets.extend(artifact_files())
    targets.extend(explicit_arg_files(sys.argv[1:]))

    unique: list[Path] = []
    seen: set[Path] = set()
    for target in targets:
        try:
            resolved = target.resolve()
            resolved.relative_to(ROOT)
        except Exception:
            continue
        if resolved not in seen and resolved.exists() and resolved.is_file():
            seen.add(resolved)
            unique.append(resolved)

    failures: list[str] = []
    for path in unique:
        for issue in path_issues(path):
            failures.append(f"{rel(path)}: {issue}")
        for issue in content_issues(path):
            failures.append(f"{rel(path)}: {issue}")

    if failures:
        print("Release hygiene check failed. Private data or secrets may be included:\n")
        for item in failures:
            print(f"- {item}")
        print("\nFix the files above before packaging or publishing CALCIE.")
        return 1

    print(f"Release hygiene check passed. Scanned {len(unique)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
