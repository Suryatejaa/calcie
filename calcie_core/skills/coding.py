"""Skill: coding/codebase commands."""

import ast
import json
import os
import re
from pathlib import Path
from typing import Callable, Optional, Tuple

from calcie_core.code_tools import ReadOnlyCodeTools
from calcie_core.prompts import CODE_SKILL_PROMPT


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
        self._pending_project_task = None
        self.project_gen_provider = (os.environ.get("CALCIE_PROJECT_GEN_PROVIDER") or "auto").strip().lower()
        if self.project_gen_provider not in {"auto", "ollama", "gemini", "openai", "claude", "grok"}:
            self.project_gen_provider = "auto"
        self.project_gen_model = (os.environ.get("CALCIE_PROJECT_GEN_MODEL") or "").strip()
        if self.project_gen_provider == "ollama" and not self.project_gen_model:
            self.project_gen_model = "llama3:8b"

    def _is_confirm_intent(self, text: str) -> bool:
        normalized = (text or "").strip().lower()
        return normalized in {
            "proceed",
            "proceeed",
            "confirm",
            "yes",
            "yes do it",
            "go ahead",
            "do it",
            "continue",
            "start",
            "create it",
        }

    def _is_reserved_non_code_command(self, text: str) -> bool:
        normalized = (text or "").strip().lower()
        if not normalized:
            return False
        reserved_prefixes = (
            "vision",
            "monitor",
            "screen monitor",
            "screen vision",
            "watch my screen",
            "monitor my screen",
            "analyze my screen",
        )
        return any(normalized == prefix or normalized.startswith(prefix + " ") for prefix in reserved_prefixes)

    def is_code_command(self, user_input: str, code_tools_enabled: bool) -> bool:
        raw = (user_input or "").strip()
        if self._is_reserved_non_code_command(raw):
            return False
        if re.match(r"^\s*code\b", raw, flags=re.IGNORECASE):
            return True
        if self._looks_like_project_creation_request(raw):
            return True
        return bool(code_tools_enabled and self.code_tools.is_code_query(raw))

    def has_pending_workflow(self) -> bool:
        return self._pending_project_task is not None

    def _looks_like_project_creation_request(self, text: str) -> bool:
        lowered = (text or "").strip().lower()
        if not lowered:
            return False
        if self._is_reserved_non_code_command(lowered):
            return False
        build_verbs = {"build", "create", "make", "generate", "scaffold"}
        project_nouns = {
            "website", "site", "web app", "landing page", "portfolio", "dashboard",
            "frontend", "ui", "app", "page", "project", "api", "backend",
            "tool", "platform", "saas", "commerce", "storefront",
        }
        tech_markers = {
            "html", "css", "javascript", "vanilla javascript", "tailwind", "gsap",
            "scrolltrigger", "lenis", "react", "vite", "next.js", "design reference",
            "fastapi", "flask", "django", "node", "express", "mongodb", "postgres",
        }

        has_build_intent = any(verb in lowered for verb in build_verbs)
        has_project_shape = any(noun in lowered for noun in project_nouns)
        has_frontend_stack = any(marker in lowered for marker in tech_markers)
        return (has_build_intent and has_project_shape) or (has_build_intent and has_frontend_stack)

    def _default_projects_root(self) -> Path:
        raw_override = (os.environ.get("CALCIE_PROJECTS_DIR") or "").strip()
        if raw_override:
            return Path(os.path.expanduser(raw_override))

        home = Path.home()
        documents = home / "Documents"
        return documents / "Calcie Projects"

    def _suggest_project_slug(self, brief: str, target_hint: str = "") -> str:
        hint = Path((target_hint or "").strip().strip("'\"")).name
        if hint and hint not in {".", "./"}:
            base = re.sub(r"[^a-zA-Z0-9._-]+", "-", hint).strip("-.").lower()
            if base:
                return base

        lowered = (brief or "").lower()
        if "landing page" in lowered:
            return "landing-page"
        if "api" in lowered:
            return "api-service"
        if "web app" in lowered:
            return "web-app"
        if "dashboard" in lowered:
            return "dashboard-ui"
        if "website" in lowered:
            return "website-project"
        if "frontend" in lowered:
            return "frontend-project"
        return "calcie-project"

    def _extract_project_target_path(self, text: str) -> Optional[str]:
        raw = (text or "").strip()
        lowered = raw.lower()
        if lowered in {
            "here",
            "current folder",
            "current directory",
            "this folder",
            "use current folder",
            "default",
            "documents",
        }:
            return "."

        quoted = re.findall(r"['\"]([^'\"]+)['\"]", raw)
        if quoted:
            return quoted[0].strip()

        match = re.search(
            r"\b(?:in|at|under|inside|into|create in|make in)\s+([~./\\\w -][^,:;]*)$",
            raw,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1).strip().strip("'\"")

        compact = raw.strip().strip("'\"")
        if compact and len(compact.split()) <= 4 and not re.search(r"\b(proceed|confirm|cancel|stop)\b", lowered):
            return compact
        return None

    def _resolve_scaffold_path(self, target_path: str) -> Tuple[bool, Optional[Path], str]:
        raw = (target_path or "").strip()
        if not raw:
            return False, None, "Missing target path."
        root = self._default_projects_root().expanduser()
        slug = self._suggest_project_slug(self._pending_project_task.get("brief", ""), raw) if self._pending_project_task else self._suggest_project_slug("", raw)

        candidate = Path(os.path.expanduser(raw))
        if raw in {".", "./"}:
            path = root / slug
        elif candidate.is_absolute():
            path = root / candidate.name
        else:
            path = root / candidate.name

        return True, path, ""

    def _scaffold_generated_project(self, brief: str, target_path: str) -> Tuple[str, str]:
        ok, root, msg = self._resolve_scaffold_path(target_path)
        if not ok or root is None:
            return msg, "Project creation failed."

        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return f"Could not create directory: {exc}", "Project creation failed."

        existing = [p.name for p in root.iterdir() if p.name not in {".DS_Store"}]
        if existing:
            return (
                f"Target path `{root}` is not empty. "
                "Give me a different project name/path and I will scaffold there safely.",
                "Project path needs confirmation.",
            )

        manifest = self._generate_project_manifest(brief, root.name)
        if not manifest:
            return (
                "I could not generate a valid project scaffold from the model right now. "
                "Try again, or switch `CALCIE_PROJECT_GEN_PROVIDER=ollama` if you want local generation.",
                "Project generation failed.",
            )

        ok, write_msg = self._write_project_manifest(root, manifest)
        if not ok:
            return write_msg, "Project creation failed."

        summary = self._summarize_brief(brief)
        return (
            f"Project scaffold created at `{root}`.\n\n"
            f"Brief remembered: {summary}\n"
            f"Files created: {', '.join(item['path'] for item in manifest['files'])}\n\n"
            "Next, I can refine the generated UI, replace placeholder content, or extend the project structure.",
            "Project scaffold created.",
        )

    def _summarize_brief(self, brief: str) -> str:
        compact = re.sub(r"\s+", " ", (brief or "").strip())
        if len(compact) <= 220:
            return compact
        return compact[:217].rstrip() + "..."

    def _extract_json_payload(self, text: str) -> Optional[dict]:
        raw = (text or "").strip()
        if not raw:
            return None

        fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
        if fence:
            raw = fence.group(1)
        else:
            obj = re.search(r"(\{.*\})", raw, flags=re.DOTALL)
            if obj:
                raw = obj.group(1)

        try:
            data = json.loads(raw)
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def _guess_project_spec(self, brief: str, project_name: str) -> dict:
        lowered = (brief or "").lower()
        libraries = []
        for lib in ("tailwind", "gsap", "scrolltrigger", "lenis", "react", "vite", "next.js", "fastapi"):
            if lib in lowered:
                libraries.append(lib)

        sections = []
        for section in ("hero", "projects", "about", "contact", "testimonials", "services", "faq"):
            if section in lowered:
                sections.append(section)

        features = []
        if "video" in lowered:
            features.append("video background placeholder")
        if "infinite scroll" in lowered:
            features.append("infinite scrolling list or marquee")
        if "scroll" in lowered or "animation" in lowered:
            features.append("scroll-driven reveal animations")
        if "smooth" in lowered:
            features.append("smooth momentum-based scrolling")

        project_kind = "website"
        if "dashboard" in lowered:
            project_kind = "dashboard"
        elif "landing page" in lowered:
            project_kind = "landing page"
        elif "portfolio" in lowered:
            project_kind = "portfolio"
        elif "api" in lowered or "backend" in lowered:
            project_kind = "api"
        elif "web app" in lowered or "app" in lowered:
            project_kind = "web app"

        target_stack = "static html + css + javascript"
        if "fastapi" in lowered or "python api" in lowered:
            target_stack = "fastapi"
        elif "react" in lowered or "vite" in lowered:
            target_stack = "react + vite"
        elif "next.js" in lowered or "next " in lowered:
            target_stack = "next.js"
        elif "node" in lowered or "express" in lowered:
            target_stack = "node + express"

        return {
            "project_name": project_name,
            "project_kind": project_kind,
            "primary_goal": self._summarize_brief(brief),
            "target_stack": target_stack,
            "design_reference": "user-provided brief",
            "must_have_sections": sections or ["hero", "content"],
            "must_have_features": features or ["project-specific UI based on brief"],
            "libraries": libraries,
            "constraints": [
                "avoid placeholder copy",
                "adapt output tightly to the brief",
                "keep project small and editable",
            ],
        }

    def _generate_project_spec(self, brief: str, project_name: str) -> dict:
        raw = self.llm_collect_text(
            [
                {
                    "role": "system",
                    "content": (
                        "You analyze software build briefs. Return strict JSON only. No markdown. "
                        "Schema: "
                        "{\"project_name\":\"...\",\"project_kind\":\"...\",\"primary_goal\":\"...\","
                        "\"target_stack\":\"...\",\"design_reference\":\"...\","
                        "\"must_have_sections\":[\"...\"],\"must_have_features\":[\"...\"],"
                        "\"libraries\":[\"...\"],\"constraints\":[\"...\"]}. "
                        "Use the user's exact requested technologies and UX constraints when present."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Project name: {project_name}\nBrief: {brief}",
                },
            ],
            max_output_tokens=min(max(self.code_max_output_tokens, 1200), 2200),
            forced_provider=self.project_gen_provider,
            forced_model=self.project_gen_model,
        )
        payload = self._extract_json_payload(raw)
        if not payload:
            return self._guess_project_spec(brief, project_name)

        normalized = self._guess_project_spec(brief, project_name)
        for key in ("project_name", "project_kind", "primary_goal", "target_stack", "design_reference"):
            value = str(payload.get(key) or "").strip()
            if value:
                normalized[key] = value
        for key in ("must_have_sections", "must_have_features", "libraries", "constraints"):
            value = payload.get(key)
            if isinstance(value, list):
                cleaned = [str(item).strip() for item in value if str(item).strip()]
                if cleaned:
                    normalized[key] = cleaned
        return normalized

    def _normalize_file_path(self, path_value: str) -> Optional[str]:
        rel = str(path_value or "").strip().replace("\\", "/")
        if not rel or rel.startswith("/"):
            return None
        parts = Path(rel).parts
        if ".." in parts:
            return None
        return rel

    def _default_file_plan(self, spec: dict) -> dict:
        stack = (spec.get("target_stack") or "").lower()
        files = [
            {
                "path": "README.md",
                "purpose": "Brief project overview and setup notes",
                "must_include": ["project goal", "stack summary", "run or open instructions"],
            }
        ]
        if "fastapi" in stack:
            files.extend(
                [
                    {"path": "requirements.txt", "purpose": "Python dependencies", "must_include": ["fastapi", "uvicorn"]},
                    {"path": "app/main.py", "purpose": "FastAPI entry point and routes", "must_include": spec.get("must_have_features", [])[:4]},
                    {"path": "app/schemas.py", "purpose": "Pydantic models and request/response shapes", "must_include": ["request models", "response models"]},
                    {"path": ".env.example", "purpose": "Environment variable template", "must_include": ["example configuration values"]},
                ]
            )
        elif "node" in stack or "express" in stack:
            files.extend(
                [
                    {"path": "package.json", "purpose": "Node scripts and dependencies", "must_include": ["express", "scripts"]},
                    {"path": "server.js", "purpose": "Express entry point and routes", "must_include": spec.get("must_have_features", [])[:4]},
                    {"path": ".env.example", "purpose": "Environment variable template", "must_include": ["example configuration values"]},
                ]
            )
        elif "next.js" in stack:
            files.extend(
                [
                    {"path": "package.json", "purpose": "Next.js scripts and dependencies", "must_include": ["next", "scripts"]},
                    {"path": "app/page.js", "purpose": "Primary route page", "must_include": spec.get("must_have_features", [])[:4]},
                    {"path": "app/globals.css", "purpose": "Global styling layer", "must_include": spec.get("libraries", [])[:3]},
                    {"path": "components/README.md", "purpose": "Component split guidance", "must_include": ["component boundaries", "how to extend"]},
                ]
            )
        elif "react" in stack or "vite" in stack:
            files.extend(
                [
                    {"path": "index.html", "purpose": "Vite HTML shell", "must_include": ["root mount node"]},
                    {"path": "package.json", "purpose": "Project scripts and dependencies", "must_include": ["vite", "dependencies"]},
                    {"path": "src/main.js", "purpose": "App bootstrap", "must_include": ["import styles", "mount app"]},
                    {"path": "src/app.js", "purpose": "Main UI markup and interactions", "must_include": spec.get("must_have_features", [])[:4]},
                    {"path": "src/styles.css", "purpose": "Primary styling layer", "must_include": spec.get("libraries", [])[:2]},
                ]
            )
        else:
            files.extend(
                [
                    {"path": "index.html", "purpose": "Main page structure", "must_include": spec.get("must_have_sections", [])[:4]},
                    {"path": "styles.css", "purpose": "Primary styling layer", "must_include": spec.get("libraries", [])[:3]},
                    {"path": "main.js", "purpose": "Interactions and animations", "must_include": spec.get("must_have_features", [])[:4]},
                ]
            )
        files.append(
            {
                "path": "assets/README.md",
                "purpose": "Lists expected replaceable assets such as video, imagery, icons, and audio",
                "must_include": ["placeholder assets", "where to replace them"],
            }
        )
        return {
            "project_name": spec.get("project_name") or "calcie-project",
            "summary": spec.get("primary_goal") or "Project generated from user brief.",
            "files": files,
        }

    def _generate_file_plan(self, brief: str, project_name: str, spec: dict) -> dict:
        raw = self.llm_collect_text(
            [
                {
                    "role": "system",
                    "content": (
                        "You design implementation plans for small software projects. Return strict JSON only. No markdown. "
                        "Schema: {\"project_name\":\"...\",\"summary\":\"...\",\"files\":["
                        "{\"path\":\"relative/path\",\"purpose\":\"...\",\"must_include\":[\"...\"]}"
                        "]}. "
                        "Rules: keep file count between 4 and 8, prefer directly runnable scaffolds, "
                        "and choose files that fit the requested stack instead of generic placeholders."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Project name: {project_name}\n"
                        f"Brief: {brief}\n"
                        f"Spec JSON: {json.dumps(spec, ensure_ascii=True)}"
                    ),
                },
            ],
            max_output_tokens=min(max(self.code_max_output_tokens, 1600), 2600),
            forced_provider=self.project_gen_provider,
            forced_model=self.project_gen_model,
        )
        payload = self._extract_json_payload(raw)
        fallback = self._default_file_plan(spec)
        if not payload:
            return fallback

        files = payload.get("files")
        if not isinstance(files, list) or not files:
            return fallback

        normalized_files = []
        for item in files[:8]:
            if not isinstance(item, dict):
                continue
            rel = self._normalize_file_path(item.get("path"))
            if not rel:
                continue
            purpose = str(item.get("purpose") or "").strip() or "Generated file"
            must_include = item.get("must_include")
            if not isinstance(must_include, list):
                must_include = []
            must_include = [str(entry).strip() for entry in must_include if str(entry).strip()][:8]
            normalized_files.append({"path": rel, "purpose": purpose, "must_include": must_include})

        if not normalized_files:
            return fallback

        return {
            "project_name": str(payload.get("project_name") or project_name).strip() or project_name,
            "summary": str(payload.get("summary") or spec.get("primary_goal") or "").strip() or fallback["summary"],
            "files": normalized_files,
        }

    def _generate_file_content(self, brief: str, spec: dict, plan: dict, file_plan: dict) -> str:
        must_include = file_plan.get("must_include") or []
        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "You generate one project file at a time. Return only the exact file content. No markdown fences. "
                    "Honor the provided project brief, project spec, and file plan. "
                    "Do not use filler placeholders like 'Welcome to my site', 'sample portfolio', or lorem ipsum. "
                    "If a library is requested, wire it in concretely. "
                    "Assume sibling files in the plan will also be generated."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Project brief:\n{brief}\n\n"
                    f"Project spec JSON:\n{json.dumps(spec, ensure_ascii=True)}\n\n"
                    f"Project file plan JSON:\n{json.dumps(plan, ensure_ascii=True)}\n\n"
                    f"Generate file: {file_plan['path']}\n"
                    f"Purpose: {file_plan['purpose']}\n"
                    f"Must include: {json.dumps(must_include, ensure_ascii=True)}"
                ),
            },
        ]
        content = self.llm_collect_text(
            prompt_messages,
            max_output_tokens=max(self.code_max_output_tokens, 2600),
            forced_provider=self.project_gen_provider,
            forced_model=self.project_gen_model,
        )
        return self.extract_updated_file_payload(content).strip()

    def _generate_file_content_with_retry(self, brief: str, spec: dict, plan: dict, file_plan: dict) -> str:
        first_pass = self._generate_file_content(brief, spec, plan, file_plan)
        lowered = first_pass.lower()
        generic_markers = ["welcome to my site", "sample portfolio", "lorem ipsum", "coming soon"]
        if first_pass and not any(marker in lowered for marker in generic_markers):
            return first_pass

        retry_messages = [
            {
                "role": "system",
                "content": (
                    "You are revising a weak project file generation. Return only the exact file content. No markdown. "
                    "The previous draft was too generic. Replace placeholders with brief-specific implementation."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Project brief:\n{brief}\n\n"
                    f"Project spec JSON:\n{json.dumps(spec, ensure_ascii=True)}\n\n"
                    f"Project file plan JSON:\n{json.dumps(plan, ensure_ascii=True)}\n\n"
                    f"Target file: {file_plan['path']}\n"
                    f"Purpose: {file_plan['purpose']}\n"
                    f"Must include: {json.dumps(file_plan.get('must_include') or [], ensure_ascii=True)}\n\n"
                    f"Bad previous draft:\n{first_pass}"
                ),
            },
        ]
        revised = self.llm_collect_text(
            retry_messages,
            max_output_tokens=max(self.code_max_output_tokens, 2600),
            forced_provider=self.project_gen_provider,
            forced_model=self.project_gen_model,
        )
        return self.extract_updated_file_payload(revised).strip()

    def _manifest_required_markers(self, brief: str, spec: dict) -> list:
        lowered = (brief or "").lower()
        markers = []
        mapping = {
            "tailwind": "tailwind",
            "gsap": "gsap",
            "scrolltrigger": "scrolltrigger",
            "lenis": "lenis",
            "video": "video",
            "hero": "hero",
        }
        for needle, marker in mapping.items():
            if needle in lowered:
                markers.append(marker)
        for item in spec.get("libraries", []):
            marker = str(item).strip().lower()
            if marker and marker not in markers:
                markers.append(marker)
        return markers

    def _manifest_is_generic(self, manifest: dict, brief: str, spec: dict) -> Tuple[bool, str]:
        files = manifest.get("files") or []
        if not files:
            return True, "Generated manifest was empty."

        combined = "\n".join(str(item.get("content") or "") for item in files).lower()
        generic_markers = [
            "welcome to my site",
            "sample portfolio",
            "lorem ipsum",
            "your project here",
            "coming soon",
        ]
        for marker in generic_markers:
            if marker in combined:
                return True, f"Generated output still contains generic placeholder text: '{marker}'."

        required_markers = self._manifest_required_markers(brief, spec)
        missing = [marker for marker in required_markers if marker not in combined]
        if missing:
            return True, "Generated output ignored key brief requirements: " + ", ".join(missing)

        paths = {str(item.get("path") or "") for item in files}
        if "index.html" not in paths and "src/main.js" not in paths:
            return True, "Generated output missed the main entry file."
        return False, ""

    def _generate_project_manifest(self, brief: str, project_name: str) -> Optional[dict]:
        spec = self._generate_project_spec(brief, project_name)
        plan = self._generate_file_plan(brief, project_name, spec)
        generated_files = []

        for file_plan in plan.get("files", [])[:8]:
            rel = self._normalize_file_path(file_plan.get("path"))
            if not rel:
                continue
            content = self._generate_file_content_with_retry(brief, spec, plan, file_plan)
            if not content:
                return None
            generated_files.append({"path": rel, "content": content})

        manifest = {
            "project_name": spec.get("project_name") or project_name,
            "files": generated_files,
        }
        is_generic, _ = self._manifest_is_generic(manifest, brief, spec)
        if is_generic:
            return None
        return manifest

    def _write_project_manifest(self, root: Path, manifest: dict) -> Tuple[bool, str]:
        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            return False, "Generated manifest did not include any files."

        written = []
        try:
            for item in files:
                if not isinstance(item, dict):
                    continue
                rel = str(item.get("path") or "").strip().replace("\\", "/")
                content = str(item.get("content") or "")
                if not rel or rel.startswith("/") or ".." in Path(rel).parts:
                    continue
                target = (root / rel).resolve()
                try:
                    target.relative_to(root.resolve())
                except ValueError:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                written.append(rel)
        except OSError as exc:
            return False, f"Failed while writing generated project files: {exc}"

        if not written:
            return False, "Model output was unusable: no safe files were generated."
        manifest["files"] = [{"path": rel, "content": ""} for rel in written]
        return True, ""

    def _handle_pending_project_task(self, user_input: str):
        if not self._pending_project_task:
            return None, None

        raw = (user_input or "").strip()
        normalized = raw.lower()
        if normalized in {"cancel", "stop", "drop it", "forget it"}:
            self._pending_project_task = None
            return "Project creation canceled. I dropped the pending brief.", "Project creation canceled."

        if self._is_confirm_intent(normalized):
            target_path = (self._pending_project_task.get("target_path") or "").strip()
            if not target_path:
                return (
                    "I am ready to build it, but I still need the target path first. Reply with something like `my-site`, `./client-app`, or `here`.",
                    "Waiting for project path.",
                )
            brief = self._pending_project_task.get("brief", "")
            self._pending_project_task = None
            return self._scaffold_generated_project(brief, target_path)

        if self._looks_like_project_creation_request(raw):
            target_path = self._pending_project_task.get("target_path") if self._pending_project_task else None
            self._pending_project_task = {"brief": raw, "target_path": target_path or ""}
            return (
                "I updated the build brief in memory. "
                "Now give me the project name or path hint, for example `my-site` or `landing-page`. "
                "When you say `proceed`, I will analyze the brief, plan the file structure, and generate the project under your Documents/Calcie Projects folder.",
                "Updated project brief. Waiting for path.",
            )

        target_path = self._extract_project_target_path(raw)
        if not target_path:
            return (
                "I still need the target path before I start coding. Reply with something like `my-site`, `./client-app`, `create it in landing-page`, or `here`.",
                "Waiting for project path.",
            )

        self._pending_project_task["target_path"] = target_path
        _, resolved, _ = self._resolve_scaffold_path(target_path)
        resolved_text = str(resolved) if resolved is not None else target_path
        return (
            f"I am ready to build the project in `{resolved_text}`. "
            "Say `proceed` and I will analyze the brief, choose the file plan, and generate the project there. "
            "Or send a different project name/path hint.",
            "Project path captured. Waiting for proceed.",
        )

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
                    f"{CODE_SKILL_PROMPT} "
                    "Read-only unless user explicitly requests propose/apply workflow."
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
        pending_response = self._handle_pending_project_task(raw)
        if pending_response != (None, None):
            return pending_response
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

        if self._looks_like_project_creation_request(raw):
            self._pending_project_task = {"brief": raw, "target_path": ""}
            return (
                "This sounds like a real build request, so I am switching into project-builder mode. "
                "Give me the project name or path hint, for example `my-site` or `dashboard-ui`. "
                "I will create it under your Documents/Calcie Projects folder. "
                "After that, say `proceed` and I will analyze the brief, plan the project structure, and generate the files there while keeping this brief in memory.",
                "Coding workflow started. Waiting for project path.",
            )

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
