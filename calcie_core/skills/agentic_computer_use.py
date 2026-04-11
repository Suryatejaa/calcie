"""Skill: agentic computer-use orchestration across app/search/computer tools."""

from __future__ import annotations

import json
import os
import re
from typing import Callable, Dict, List, Optional, Tuple


class AgenticComputerUseSkill:
    """Multi-step task orchestrator for essential real-world tasks only."""

    VALID_PROVIDERS = {"auto", "openai", "gemini", "claude"}

    def __init__(
        self,
        llm_collect_text: Callable[[list, int, Optional[str]], str],
        app_skill,
        computer_skill,
        searching_skill,
    ):
        self.llm_collect_text = llm_collect_text
        self.app_skill = app_skill
        self.computer_skill = computer_skill
        self.searching_skill = searching_skill

        self.enabled = self._env_bool("CALCIE_AGENTIC_COMPUTER_USE_ENABLED", True)
        self.essential_only = self._env_bool("CALCIE_AGENTIC_COMPUTER_USE_ESSENTIAL_ONLY", True)
        self.max_steps = self._env_int("CALCIE_COMPUTER_USE_MAX_STEPS", 6, 2, 12)
        self.require_arm = self._env_bool("CALCIE_COMPUTER_USE_AUTO_ARM", True)
        self.require_confirm = self._env_bool("CALCIE_COMPUTER_USE_REQUIRE_CONFIRM", True)
        self.provider = (os.environ.get("CALCIE_COMPUTER_USE_PROVIDER") or "auto").strip().lower()
        if self.provider not in self.VALID_PROVIDERS:
            self.provider = "auto"
        self._pending_plan: Optional[Dict] = None

    def handle_command(self, user_input: str) -> Tuple[Optional[str], Optional[str]]:
        raw = (user_input or "").strip()
        if not raw or not self.enabled:
            return None, None

        pending_response = self._handle_pending_confirmation(raw)
        if pending_response is not None:
            return pending_response, pending_response

        if not self._should_trigger(raw):
            return None, None
        if self.essential_only and not self._is_essential_task(raw):
            return None, None

        plan = self._build_plan(raw)
        plan = self._sanitize_plan(plan, raw) if plan else None
        if not plan:
            plan = self._heuristic_plan(raw)
            if not plan:
                return None, None

        if self.require_confirm and self._plan_requires_confirmation(plan):
            self._pending_plan = {
                "original_input": raw,
                "plan": plan,
            }
            preview = self._preview_plan(plan)
            return preview, preview

        results = self._execute_plan(plan, raw)
        response = self._format_response(raw, plan, results)
        return response, response

    def _handle_pending_confirmation(self, user_input: str) -> Optional[str]:
        if not self._pending_plan:
            return None

        normalized = self._normalize(user_input)
        if self._is_confirm_intent(normalized):
            pending = self._pending_plan
            self._pending_plan = None
            plan = pending.get("plan") or {}
            original = pending.get("original_input") or user_input
            results = self._execute_plan(plan, original)
            return self._format_response(original, plan, results)

        if self._is_cancel_intent(normalized):
            self._pending_plan = None
            return "Agentic task canceled. I did not execute any actions."

        if self._should_trigger(user_input):
            old_goal = (self._pending_plan.get("plan") or {}).get("goal") or "pending task"
            self._pending_plan = None
            return (
                f"Previous pending task dropped: {old_goal}. "
                "I will plan the new request now. Say it again to continue."
            )

        return "Pending agentic task detected. Say `confirm` to execute or `cancel` to drop it."

    def _should_trigger(self, text: str) -> bool:
        normalized = self._normalize(text)
        if not normalized:
            return False
        triggers = [
            "order",
            "buy",
            "checkout",
            "book",
            "watch",
            "play movie",
            "netflix",
            "prime video",
            "amazon",
            "add to cart",
            "complete this for me",
            "do this on my screen",
            "use computer",
            "real computer use",
        ]
        if any(t in normalized for t in triggers):
            return True
        if " then " in normalized and any(t in normalized for t in ["open", "search", "click", "type"]):
            return True
        return False

    def _is_essential_task(self, text: str) -> bool:
        normalized = self._normalize(text)
        essential_markers = [
            "order",
            "buy",
            "checkout",
            "book",
            "amazon",
            "flipkart",
            "netflix",
            "prime video",
            "disney",
            "movie",
            "reserve",
            "subscription",
            "payment",
            "ticket",
        ]
        return any(m in normalized for m in essential_markers)

    def _build_plan(self, user_input: str) -> Optional[Dict]:
        system_prompt = (
            "You are a desktop task planner. "
            "Return only strict JSON. No markdown. "
            "Goal: create a safe, concise action plan using available tools.\n"
            "Allowed tools:\n"
            "1) app.open_app {app}\n"
            "2) app.open_target_in_app {target, app}\n"
            "3) app.play {command}\n"
            "4) search.query {query}\n"
            "5) computer.command {command}\n"
            "6) say {text}\n"
            "Output schema:\n"
            "{"
            "\"goal\":\"string\","
            "\"risk\":\"low|medium|high\","
            "\"steps\":[{\"tool\":\"...\",\"args\":{...},\"why\":\"string\"}]"
            "}\n"
            "Rules:\n"
            "- max 6 steps\n"
            "- never finalize payment/place order\n"
            "- for shopping: stop at cart/review stage\n"
            "- for movie playback: open platform search/title and start playback page\n"
            "- use specific URL targets for app.open_target_in_app when helpful\n"
            "- steps must be executable by tools exactly\n"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        raw = self.llm_collect_text(messages, max_output_tokens=650, forced_provider=self.provider).strip()
        return self._parse_plan(raw)

    def _parse_plan(self, text: str) -> Optional[Dict]:
        if not text:
            return None
        candidate = text
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        if fence:
            candidate = fence.group(1)
        else:
            obj_match = re.search(r"(\{.*\})", text, flags=re.DOTALL)
            if obj_match:
                candidate = obj_match.group(1)

        try:
            data = json.loads(candidate)
        except Exception:
            return None

        if not isinstance(data, dict):
            return None
        steps = data.get("steps")
        if not isinstance(steps, list) or not steps:
            return None

        cleaned_steps = []
        for step in steps[: self.max_steps]:
            if not isinstance(step, dict):
                continue
            tool = str(step.get("tool") or "").strip().lower()
            args = step.get("args")
            if not isinstance(args, dict):
                args = {}
            if tool not in {"app.open_app", "app.open_target_in_app", "app.play", "search.query", "computer.command", "say"}:
                continue
            cleaned_steps.append({"tool": tool, "args": args, "why": str(step.get("why") or "").strip()})

        if not cleaned_steps:
            return None

        return {
            "goal": str(data.get("goal") or "").strip() or "Complete the requested task safely",
            "risk": str(data.get("risk") or "medium").strip().lower(),
            "steps": cleaned_steps,
        }

    def _heuristic_plan(self, user_input: str) -> Optional[Dict]:
        normalized = self._normalize(user_input)
        # Shopping flow template.
        if any(k in normalized for k in ["order", "buy", "amazon", "checkout"]):
            item = self._extract_item(user_input) or "requested product"
            target = f"https://www.amazon.in/s?k={self._url_encode(item)}"
            return {
                "goal": f"Open Amazon and navigate toward ordering {item} (without final payment).",
                "risk": "high",
                "steps": [
                    {"tool": "app.open_target_in_app", "args": {"target": target, "app": "chrome"}, "why": "Open Amazon search for the item"},
                    {"tool": "say", "args": {"text": "Amazon opened. I stopped before payment. Say confirm to proceed with cart/review actions."}, "why": "Safety stop"},
                ],
            }

        # OTT movie template.
        if any(k in normalized for k in ["movie", "watch", "netflix", "prime video"]):
            title = self._extract_movie_title(user_input) or "requested movie"
            if "netflix" in normalized:
                target = f"https://www.netflix.com/search?q={self._url_encode(title)}"
            elif "prime" in normalized:
                target = f"https://www.primevideo.com/search/ref=atv_nb_sr?phrase={self._url_encode(title)}"
            else:
                target = f"https://www.google.com/search?q={self._url_encode(title + ' movie streaming')}"
            return {
                "goal": f"Find and open playback page for {title}.",
                "risk": "medium",
                "steps": [
                    {"tool": "app.open_target_in_app", "args": {"target": target, "app": "chrome"}, "why": "Open platform search"},
                    {"tool": "say", "args": {"text": "Search page opened. I can continue with click/type steps if needed."}, "why": "Ask for next refinement"},
                ],
            }

        return None

    def _execute_plan(self, plan: Dict, original_input: str) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        steps = plan.get("steps") or []
        fail_streak = 0

        if self.require_arm:
            self.computer_skill.handle_command("control arm")

        for index, step in enumerate(steps[: self.max_steps], start=1):
            tool = step.get("tool", "")
            args = step.get("args") or {}
            status = "ok"
            output = ""

            try:
                if tool == "app.open_app":
                    app = (args.get("app") or "").strip()
                    output = self.app_skill.open_app(app) if app else "Missing app name."
                    lowered_output = output.lower()
                    if "failed" in lowered_output or "unable to find application" in lowered_output:
                        status = "failed"

                elif tool == "app.open_target_in_app":
                    target = (args.get("target") or "").strip()
                    app = (args.get("app") or "chrome").strip()
                    output = self.app_skill.open_target_in_app(target, app)
                    if output.lower().startswith("failed"):
                        status = "failed"

                elif tool == "app.play":
                    command = (args.get("command") or "").strip()
                    if not command:
                        output = "Missing play command."
                        status = "failed"
                    else:
                        resp, _ = self.app_skill.handle_command(command)
                        output = resp or "Play command was not handled."
                        if resp is None or "not handled" in output.lower() or output.lower().startswith("failed"):
                            status = "failed"

                elif tool == "search.query":
                    query = (args.get("query") or "").strip()
                    if not query:
                        output = "Missing search query."
                        status = "failed"
                    else:
                        resp, _ = self.searching_skill.handle_query(f"search {query}")
                        output = (resp or "No search result.")[:500]
                        if resp is None:
                            status = "failed"

                elif tool == "computer.command":
                    command = (args.get("command") or "").strip()
                    if not command:
                        output = "Missing computer command."
                        status = "failed"
                    else:
                        resp, _ = self.computer_skill.handle_command(command)
                        output = resp or "No computer response."
                        if resp is None or "failed" in output.lower():
                            status = "failed"

                elif tool == "say":
                    output = (args.get("text") or "").strip() or "Step note."

                else:
                    status = "failed"
                    output = f"Unsupported tool step: {tool}"
            except Exception as exc:
                status = "failed"
                output = f"{tool} exception: {exc}"

            results.append(
                {
                    "step": str(index),
                    "tool": tool,
                    "status": status,
                    "output": output,
                    "why": step.get("why", ""),
                }
            )

            if status == "failed":
                fail_streak += 1
            else:
                fail_streak = 0
            if fail_streak >= 2:
                results.append(
                    {
                        "step": str(index + 1),
                        "tool": "say",
                        "status": "ok",
                        "output": "Stopping execution after repeated failed steps. I can retry with a refined instruction.",
                        "why": "safety stop",
                    }
                )
                break

        return results

    def _sanitize_plan(self, plan: Optional[Dict], user_input: str) -> Optional[Dict]:
        if not plan or not isinstance(plan, dict):
            return None
        steps = plan.get("steps")
        if not isinstance(steps, list) or not steps:
            return None

        kind = self._task_kind(user_input)
        normalized = self._normalize(user_input)
        item = self._extract_item(user_input) or "requested product"
        movie = self._extract_movie_title(user_input) or "requested movie"

        rewritten: List[Dict] = []
        for step in steps[: self.max_steps]:
            if not isinstance(step, dict):
                continue
            tool = str(step.get("tool") or "").strip().lower()
            args = step.get("args") if isinstance(step.get("args"), dict) else {}
            why = str(step.get("why") or "").strip()

            if tool == "app.open_app":
                app = str(args.get("app") or "").strip()
                app_l = app.lower()
                if app_l in {"amazon", "amazon.in", "amazon.com"}:
                    tool = "app.open_target_in_app"
                    args = {"target": f"https://www.amazon.in/s?k={self._url_encode(item)}", "app": "chrome"}
                elif app_l in {"netflix", "prime video", "prime", "disney hotstar", "hotstar"}:
                    tool = "app.open_target_in_app"
                    if "netflix" in app_l:
                        target = f"https://www.netflix.com/search?q={self._url_encode(movie)}"
                    elif "prime" in app_l:
                        target = f"https://www.primevideo.com/search/ref=atv_nb_sr?phrase={self._url_encode(movie)}"
                    else:
                        target = f"https://www.google.com/search?q={self._url_encode(movie + ' streaming')}"
                    args = {"target": target, "app": "chrome"}

            elif tool == "app.open_target_in_app":
                target = str(args.get("target") or "").strip()
                app = str(args.get("app") or "chrome").strip()
                if not target:
                    continue
                # Normalize bare site words into URLs.
                if target.lower() in {"amazon", "amazon.in", "amazon.com"}:
                    target = f"https://www.amazon.in/s?k={self._url_encode(item)}"
                if target.lower() == "netflix":
                    target = f"https://www.netflix.com/search?q={self._url_encode(movie)}"
                args = {"target": target, "app": app or "chrome"}

            elif tool == "app.play":
                command = str(args.get("command") or "").strip()
                if not re.match(r"^(play|resume|continue)\b", command, flags=re.IGNORECASE):
                    if kind == "movie":
                        platform = "netflix" if "netflix" in normalized else "prime video" if "prime" in normalized else "netflix"
                        target = (
                            f"https://www.netflix.com/search?q={self._url_encode(movie)}"
                            if platform == "netflix"
                            else f"https://www.primevideo.com/search/ref=atv_nb_sr?phrase={self._url_encode(movie)}"
                        )
                        tool = "app.open_target_in_app"
                        args = {"target": target, "app": "chrome"}
                    elif kind == "shopping":
                        # app.play has no meaning for shopping flow.
                        continue
                    else:
                        continue
                else:
                    args = {"command": command}

            elif tool == "search.query":
                query = str(args.get("query") or "").strip()
                if not query:
                    continue
                args = {"query": query}

            elif tool == "computer.command":
                command = str(args.get("command") or "").strip()
                if not command:
                    continue
                # Block explicitly dangerous deletes/resets from planner output.
                blocked = ("rm ", "git reset", "shutdown", "reboot")
                if any(b in command.lower() for b in blocked):
                    continue
                args = {"command": command}

            elif tool == "say":
                text = str(args.get("text") or "").strip()
                args = {"text": text or "Step completed."}

            else:
                continue

            rewritten.append({"tool": tool, "args": args, "why": why})

        rewritten = self._enforce_required_flow(rewritten, kind, item, movie, normalized)
        if not rewritten:
            return None

        return {
            "goal": str(plan.get("goal") or "").strip() or "Complete the requested task safely",
            "risk": str(plan.get("risk") or "medium").strip().lower(),
            "steps": rewritten[: self.max_steps],
        }

    def _task_kind(self, user_input: str) -> str:
        normalized = self._normalize(user_input)
        if any(k in normalized for k in ["order", "buy", "checkout", "cart", "amazon", "flipkart"]):
            return "shopping"
        if any(k in normalized for k in ["movie", "watch", "netflix", "prime video", "disney", "hotstar"]):
            return "movie"
        return "general"

    def _enforce_required_flow(
        self,
        steps: List[Dict],
        kind: str,
        item: str,
        movie: str,
        normalized_input: str,
    ) -> List[Dict]:
        out = list(steps)
        has_open_target = any(s.get("tool") == "app.open_target_in_app" for s in out)

        if kind == "shopping" and not has_open_target:
            out.insert(
                0,
                {
                    "tool": "app.open_target_in_app",
                    "args": {"target": f"https://www.amazon.in/s?k={self._url_encode(item)}", "app": "chrome"},
                    "why": "Open product search first",
                },
            )

        if kind == "movie" and not has_open_target:
            if "netflix" in normalized_input:
                target = f"https://www.netflix.com/search?q={self._url_encode(movie)}"
            elif "prime" in normalized_input:
                target = f"https://www.primevideo.com/search/ref=atv_nb_sr?phrase={self._url_encode(movie)}"
            else:
                target = f"https://www.google.com/search?q={self._url_encode(movie + ' streaming')}"
            out.insert(
                0,
                {
                    "tool": "app.open_target_in_app",
                    "args": {"target": target, "app": "chrome"},
                    "why": "Open playback search first",
                },
            )

        # Remove noisy repeated say lines; keep max one.
        say_seen = False
        compact = []
        for step in out:
            if step.get("tool") == "say":
                if say_seen:
                    continue
                say_seen = True
            compact.append(step)
        return compact

    def _format_response(self, user_input: str, plan: Dict, results: List[Dict[str, str]]) -> str:
        lines = []
        goal = plan.get("goal") or user_input
        lines.append(f"Agentic computer-use plan executed for: {goal}")
        lines.append(f"Provider: {self.provider}")
        ok_count = sum(1 for r in results if r.get("status") == "ok")
        lines.append(f"Steps completed: {ok_count}/{len(results)}")
        lines.append("")
        lines.append("Execution trace:")
        for r in results:
            tool = r.get("tool", "")
            status = r.get("status", "")
            output = (r.get("output", "") or "").strip().replace("\n", " ")
            if len(output) > 180:
                output = output[:180].rstrip() + "..."
            lines.append(f"- {r.get('step')}. [{status}] {tool} -> {output}")

        if self._looks_like_payment_request(user_input):
            lines.append("")
            lines.append("Safety stop: I do not auto-complete payment/place-order. I stop at review stage.")

        return "\n".join(lines)

    def _preview_plan(self, plan: Dict) -> str:
        goal = plan.get("goal") or "requested task"
        risk = str(plan.get("risk") or "medium").upper()
        lines = [
            f"Planned agentic task: {goal}",
            f"Risk: {risk}",
            "Proposed steps:",
        ]
        for i, step in enumerate((plan.get("steps") or [])[: self.max_steps], start=1):
            tool = step.get("tool", "")
            args = step.get("args") or {}
            lines.append(f"- {i}. {tool} {args}")
        lines.append("Say `confirm` to execute, or `cancel`.")
        return "\n".join(lines)

    def _plan_requires_confirmation(self, plan: Dict) -> bool:
        risk = str(plan.get("risk") or "").strip().lower()
        if risk in {"high", "medium"}:
            return True
        return self._contains_action_steps(plan)

    def _contains_action_steps(self, plan: Dict) -> bool:
        for step in (plan.get("steps") or []):
            tool = str((step or {}).get("tool") or "").strip().lower()
            if tool in {"app.open_app", "app.open_target_in_app", "app.play", "computer.command"}:
                return True
        return False

    def _is_confirm_intent(self, normalized: str) -> bool:
        return normalized in {"confirm", "continue", "go ahead", "proceed", "yes", "do it", "execute"}

    def _is_cancel_intent(self, normalized: str) -> bool:
        return normalized in {"cancel", "abort", "stop", "drop", "no", "dont do it", "do not"}

    def _extract_item(self, text: str) -> str:
        lowered = text.strip()
        m = re.search(r"\b(?:order|buy)\s+(.+?)(?:\s+on\s+amazon|\s+from\s+amazon|$)", lowered, flags=re.IGNORECASE)
        if m:
            item = m.group(1).strip(" .,!?:;")
            item = re.sub(r"^(?:a|an|the|some)\s+", "", item, flags=re.IGNORECASE).strip()
            return item
        return ""

    def _extract_movie_title(self, text: str) -> str:
        m = re.search(r"\b(?:watch|play)\s+(?:movie\s+)?(.+?)(?:\s+on\s+netflix|\s+on\s+prime|\s+on\s+prime video|$)", text, flags=re.IGNORECASE)
        if m:
            title = m.group(1).strip(" .,!?:;")
            title = re.sub(r"^(?:a|an|the|specific|movie)\s+", "", title, flags=re.IGNORECASE).strip()
            return title
        return ""

    def _looks_like_payment_request(self, text: str) -> bool:
        normalized = self._normalize(text)
        return any(k in normalized for k in ["pay", "payment", "place order", "checkout", "upi", "card"])

    def _normalize(self, text: str) -> str:
        text = (text or "").lower()
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _url_encode(self, text: str) -> str:
        from urllib.parse import quote_plus

        return quote_plus((text or "").strip())

    def _env_bool(self, name: str, default: bool) -> bool:
        raw = (os.environ.get(name) or "").strip().lower()
        if not raw:
            return default
        return raw in {"1", "true", "yes", "on"}

    def _env_int(self, name: str, default: int, min_value: int, max_value: int) -> int:
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            return default
        return max(min_value, min(max_value, value))
