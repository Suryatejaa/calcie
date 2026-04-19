"""Skill: agentic computer-use orchestration across app/search/computer tools."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Callable, Dict, List, Optional, Tuple

from calcie_core.prompts import AGENTIC_PLAN_PROMPT, TASK_INTERPRET_SYSTEM_PROMPT


class AgenticComputerUseSkill:
    """Multi-step task orchestrator for essential real-world tasks only."""

    VALID_PROVIDERS = {"auto", "openai", "gemini", "claude"}
    PLATFORM_SEARCH_URLS = {
        "amazon": "https://www.amazon.in/s?k={query}",
        "flipkart": "https://www.flipkart.com/search?q={query}",
        "swiggy": "https://www.swiggy.com/search?query={query}",
        "zomato": "https://www.zomato.com/search?q={query}",
        "blinkit": "https://blinkit.com/s/?q={query}",
        "zepto": "https://www.zeptonow.com/search?query={query}",
        "instamart": "https://www.swiggy.com/instamart/search?query={query}",
        "bigbasket": "https://www.bigbasket.com/ps/?q={query}",
        "netflix": "https://www.netflix.com/search?q={query}",
        "prime_video": "https://www.primevideo.com/search/ref=atv_nb_sr?phrase={query}",
    }

    def __init__(
        self,
        llm_collect_text: Callable[[list, int, Optional[str]], str],
        app_skill,
        computer_skill,
        searching_skill,
        vision_skill,
    ):
        self.llm_collect_text = llm_collect_text
        self.app_skill = app_skill
        self.computer_skill = computer_skill
        self.searching_skill = searching_skill
        self.vision_skill = vision_skill

        self.enabled = self._env_bool("CALCIE_AGENTIC_COMPUTER_USE_ENABLED", True)
        self.essential_only = self._env_bool("CALCIE_AGENTIC_COMPUTER_USE_ESSENTIAL_ONLY", True)
        self.max_steps = self._env_int("CALCIE_COMPUTER_USE_MAX_STEPS", 6, 2, 12)
        self.require_arm = self._env_bool("CALCIE_COMPUTER_USE_AUTO_ARM", True)
        self.require_confirm = self._env_bool("CALCIE_COMPUTER_USE_REQUIRE_CONFIRM", True)
        self.confirm_sensitive_only = self._env_bool("CALCIE_COMPUTER_USE_CONFIRM_ONLY_SENSITIVE", True)
        self.verbose_output = self._env_bool("CALCIE_AGENTIC_VERBOSE_OUTPUT", False)
        self.vision_retry_count = self._env_int("CALCIE_AGENTIC_VISION_RETRY_COUNT", 3, 1, 5)
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

        task_meta = self._interpret_task(raw)
        plan = self._build_plan(raw)
        plan = self._sanitize_plan(plan, raw, task_meta) if plan else None
        if not plan:
            plan = self._heuristic_plan(raw, task_meta)
            if not plan:
                return None, None

        if self.require_confirm and self._plan_requires_confirmation(plan, raw):
            self._pending_plan = {
                "original_input": raw,
                "plan": plan,
            }
            preview = self._preview_plan(plan)
            return preview, "Plan ready. Say confirm or cancel."

        results = self._execute_plan(plan, raw)
        response = self._format_response(raw, plan, results)
        return response, self._format_spoken_response(raw, plan, results)

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
            "flipkart",
            "swiggy",
            "zomato",
            "blinkit",
            "zepto",
            "instamart",
            "bigbasket",
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
            "swiggy",
            "zomato",
            "blinkit",
            "zepto",
            "instamart",
            "bigbasket",
            "grocery",
            "groceries",
            "biriyani",
            "biryani",
            "pizza",
            "burger",
            "momos",
        ]
        return any(m in normalized for m in essential_markers)

    def _build_plan(self, user_input: str) -> Optional[Dict]:
        system_prompt = AGENTIC_PLAN_PROMPT
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        raw = self.llm_collect_text(messages, max_output_tokens=650, forced_provider=self.provider).strip()
        return self._parse_plan(raw)

    def _interpret_task(self, user_input: str) -> Dict:
        normalized = self._normalize(user_input)
        heuristic = self._heuristic_interpretation(user_input)
        messages = [
            {"role": "system", "content": TASK_INTERPRET_SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ]
        try:
            raw = self.llm_collect_text(messages, max_output_tokens=220, forced_provider=self.provider).strip()
            parsed = self._extract_json_object(raw)
            if parsed:
                merged = dict(heuristic)
                merged.update({k: v for k, v in parsed.items() if v not in {None, ""}})
                item_query = str(merged.get("item_query") or "").strip() or heuristic.get("item_query") or ""
                merged["item_query"] = item_query
                if merged.get("platform") == "unknown":
                    merged["platform"] = heuristic.get("platform", "unknown")
                if merged.get("domain") == "general" and heuristic.get("domain") != "general":
                    merged["domain"] = heuristic.get("domain")
                if not merged.get("intent"):
                    merged["intent"] = heuristic.get("intent", "browse")
                if "needs_confirmation" not in merged:
                    merged["needs_confirmation"] = heuristic.get("needs_confirmation", False)
                return merged
        except Exception:
            pass
        if "flipkart" in normalized:
            heuristic["platform"] = "flipkart"
        return heuristic

    def _heuristic_interpretation(self, user_input: str) -> Dict:
        normalized = self._normalize(user_input)
        item_query = self._extract_item(user_input) or self._extract_movie_title(user_input) or user_input.strip()
        domain = "general"
        platform = "unknown"
        intent = "browse"

        if "zomato" in normalized:
            domain = "food_delivery"
            platform = "zomato"
        elif "swiggy" in normalized and "instamart" not in normalized:
            domain = "food_delivery"
            platform = "swiggy"
        elif any(word in normalized for word in ["zepto", "blinkit", "instamart", "bigbasket"]):
            domain = "groceries"
            if "zepto" in normalized:
                platform = "zepto"
            elif "blinkit" in normalized:
                platform = "blinkit"
            elif "instamart" in normalized:
                platform = "instamart"
            else:
                platform = "bigbasket"
        elif "flipkart" in normalized:
            domain = "shopping"
            platform = "flipkart"
        elif "amazon" in normalized:
            domain = "shopping"
            platform = "amazon"
        elif any(word in normalized for word in ["biriyani", "biryani", "pizza", "burger", "momos", "shawarma", "roll", "food", "meal"]):
            domain = "food_delivery"
            platform = "swiggy" if "swiggy" in normalized else "zomato" if "zomato" in normalized else "swiggy"
        elif any(
            word in normalized
            for word in [
                "grocery",
                "groceries",
                "milk",
                "vegetable",
                "vegetables",
                "rice",
                "atta",
                "oil",
                "bread",
                "eggs",
                "onion",
                "onions",
                "tomato",
                "tomatoes",
                "potato",
                "potatoes",
                "fruit",
                "fruits",
            ]
        ):
            domain = "groceries"
            if "zepto" in normalized:
                platform = "zepto"
            elif "blinkit" in normalized:
                platform = "blinkit"
            elif "instamart" in normalized:
                platform = "instamart"
            elif "bigbasket" in normalized:
                platform = "bigbasket"
            else:
                platform = "blinkit"
        elif any(word in normalized for word in ["amazon", "flipkart", "buy", "order", "bag", "laptop", "mattress", "mouse", "power bank", "powerbank", "airpods"]):
            domain = "shopping"
            if "flipkart" in normalized:
                platform = "flipkart"
            elif "amazon" in normalized:
                platform = "amazon"
            else:
                platform = "amazon"
        elif any(word in normalized for word in ["movie", "watch", "netflix", "prime video"]):
            domain = "movie"
            if "prime" in normalized:
                platform = "prime_video"
            else:
                platform = "netflix"
            intent = "play"

        if any(word in normalized for word in ["checkout", "pay", "place order", "payment", "upi", "card"]):
            intent = "checkout"
        elif any(word in normalized for word in ["cart", "add to cart", "review"]):
            intent = "review_only"

        return {
            "domain": domain,
            "platform": platform,
            "item_query": item_query.strip(),
            "intent": intent,
            "needs_confirmation": self._looks_like_sensitive_task(user_input),
            "reason": "heuristic",
        }

    def _extract_json_object(self, text: str) -> Optional[Dict]:
        if not text:
            return None
        candidate = text
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        if fence:
            candidate = fence.group(1)
        else:
            match = re.search(r"(\{.*\})", text, flags=re.DOTALL)
            if match:
                candidate = match.group(1)
        try:
            parsed = json.loads(candidate)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

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
            if tool not in {"app.open_app", "app.open_target_in_app", "app.play", "search.query", "computer.command", "vision.inspect", "say"}:
                continue
            cleaned_steps.append({"tool": tool, "args": args, "why": str(step.get("why") or "").strip()})

        if not cleaned_steps:
            return None

        return {
            "goal": str(data.get("goal") or "").strip() or "Complete the requested task safely",
            "risk": str(data.get("risk") or "medium").strip().lower(),
            "steps": cleaned_steps,
        }

    def _heuristic_plan(self, user_input: str, task_meta: Optional[Dict] = None) -> Optional[Dict]:
        normalized = self._normalize(user_input)
        task_meta = task_meta or self._heuristic_interpretation(user_input)
        domain = str(task_meta.get("domain") or "general").strip().lower()
        platform = str(task_meta.get("platform") or "unknown").strip().lower()
        item_query = str(task_meta.get("item_query") or "").strip() or user_input.strip()
        # Shopping flow template.
        if domain in {"shopping", "food_delivery", "groceries"}:
            item = item_query or self._extract_item(user_input) or "requested item"
            target = self._platform_search_url(platform, item)
            return {
                "goal": f"Open {self._platform_label(platform)} and navigate toward ordering {item} (without final payment).",
                "risk": "medium",
                "steps": [
                    {"tool": "app.open_target_in_app", "args": {"target": target, "app": "chrome"}, "why": "Open Amazon search for the item"},
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

                elif tool == "vision.inspect":
                    goal = (args.get("goal") or "").strip()
                    if not goal:
                        output = "Missing vision goal."
                        status = "failed"
                    else:
                        output, status = self._execute_vision_step(goal)

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

    def _sanitize_plan(self, plan: Optional[Dict], user_input: str, task_meta: Optional[Dict] = None) -> Optional[Dict]:
        if not plan or not isinstance(plan, dict):
            return None
        steps = plan.get("steps")
        if not isinstance(steps, list) or not steps:
            return None

        task_meta = task_meta or self._heuristic_interpretation(user_input)
        kind = self._task_kind(user_input, task_meta)
        normalized = self._normalize(user_input)
        item = str(task_meta.get("item_query") or "").strip() or self._extract_item(user_input) or "requested product"
        movie = self._extract_movie_title(user_input) or "requested movie"
        platform = str(task_meta.get("platform") or "unknown").strip().lower()

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
                if kind in {"shopping", "food_delivery", "groceries"} and (app_l in {"amazon", "amazon.in", "amazon.com", "flipkart", "swiggy", "zomato", "blinkit", "zepto", "instamart", "bigbasket"} or platform != "unknown"):
                    tool = "app.open_target_in_app"
                    args = {"target": self._platform_search_url(platform, item), "app": "chrome"}
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
                if target.lower() in {"amazon", "amazon.in", "amazon.com", "flipkart", "swiggy", "zomato", "blinkit", "zepto", "instamart", "bigbasket"}:
                    platform = self._normalize_platform_token(target.lower(), platform)
                    target = self._platform_search_url(platform, item)
                if target.lower() == "netflix":
                    target = f"https://www.netflix.com/search?q={self._url_encode(movie)}"
                if kind in {"shopping", "food_delivery", "groceries"}:
                    canonical_target = self._platform_search_url(platform, item)
                    normalized_target = self._normalize(target)
                    looks_like_google = "google.com/search" in target.lower()
                    looks_like_listing_noise = any(
                        token in normalized_target for token in ["listing", "shopping results", "selected result", "best result"]
                    )
                    if app.lower() in {"amazon", "amazon.in", "amazon.com", "flipkart", "swiggy", "zomato", "blinkit", "zepto", "instamart", "bigbasket"}:
                        app = "chrome"
                        target = canonical_target
                    elif not re.match(r"^https?://", target, flags=re.IGNORECASE):
                        target = canonical_target
                    elif looks_like_google or looks_like_listing_noise:
                        target = canonical_target
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
                if kind == "shopping":
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

            elif tool == "vision.inspect":
                goal = str(args.get("goal") or "").strip()
                if not goal:
                    continue
                args = {"goal": goal}

            elif tool == "say":
                text = str(args.get("text") or "").strip()
                args = {"text": text or "Step completed."}

            else:
                continue

            rewritten.append({"tool": tool, "args": args, "why": why})

        rewritten = self._enforce_required_flow(rewritten, kind, item, movie, normalized, platform=platform)
        rewritten = self._dedupe_steps(rewritten, kind, item, movie, platform)
        if not rewritten:
            return None

        return {
            "goal": str(plan.get("goal") or "").strip() or "Complete the requested task safely",
            "risk": str(plan.get("risk") or "medium").strip().lower(),
            "steps": rewritten[: self.max_steps],
        }

    def _task_kind(self, user_input: str, task_meta: Optional[Dict] = None) -> str:
        if task_meta:
            domain = str(task_meta.get("domain") or "").strip().lower()
            if domain:
                return domain
        normalized = self._normalize(user_input)
        if any(k in normalized for k in ["biriyani", "biryani", "pizza", "burger", "momos", "food", "meal"]):
            return "food_delivery"
        if any(k in normalized for k in ["grocery", "groceries", "milk", "vegetable", "rice", "atta", "oil", "onion", "tomato", "potato", "zepto", "blinkit", "instamart", "bigbasket"]):
            return "groceries"
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
        platform: str = "unknown",
    ) -> List[Dict]:
        out = list(steps)
        has_open_target = any(s.get("tool") == "app.open_target_in_app" for s in out)

        if kind in {"shopping", "food_delivery", "groceries"} and not has_open_target:
            out.insert(
                0,
                {
                    "tool": "app.open_target_in_app",
                    "args": {"target": self._platform_search_url(platform, item), "app": "chrome"},
                    "why": "Open product search first",
                },
            )

        if kind in {"shopping", "food_delivery", "groceries"} and not any(s.get("tool") == "vision.inspect" for s in out):
            if kind == "food_delivery":
                inspection_goal = (
                    f"Inspect the current {self._platform_label(platform)} results for {item}. "
                    "Find the strongest visible restaurant option using rating, delivery time, offer badges, and relevance. "
                    "If the page is still loading, set should_act=true with action_command `control scroll down 300` only if needed. "
                    "If a good restaurant card is clearly visible and localizable, set should_act=true with `control click X Y`."
                )
            elif kind == "groceries":
                inspection_goal = (
                    f"Inspect the current {self._platform_label(platform)} results for {item}. "
                    "Find the strongest visible grocery option using rating, quantity, price, and delivery cues. "
                    "If the page is still loading, wait/retry before acting. "
                    "If a strong product card is clearly visible and localizable, set should_act=true with `control click X Y`."
                )
            else:
                inspection_goal = (
                    f"Inspect the current {self._platform_label(platform)} results for {item}. "
                    "Find the strongest visible option using star rating, rating count, Prime or platform badge, and price. "
                    "If the page is not showing enough useful products yet, set should_act=true with action_command "
                    "`control scroll down 700`. "
                    "If a strong product card is clearly visible and you can localize it confidently, set should_act=true "
                    "with a safe command like `control click X Y`. "
                    "Otherwise summarize the best visible options and keep should_act=false."
                )
            insert_at = 1 if out else 0
            out.insert(
                insert_at,
                {
                    "tool": "vision.inspect",
                    "args": {"goal": inspection_goal},
                    "why": "Use screen understanding to guide browsing decisions",
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

    def _dedupe_steps(self, steps: List[Dict], kind: str, item: str, movie: str, platform: str) -> List[Dict]:
        deduped: List[Dict] = []
        seen_open_targets = set()
        seen_search_queries = set()
        canonical_target = None

        if kind in {"shopping", "food_delivery", "groceries"}:
            canonical_target = self._platform_search_url(platform, item)
        elif kind == "movie":
            if self._normalize_platform_token(platform, "netflix") == "prime_video":
                canonical_target = f"https://www.primevideo.com/search/ref=atv_nb_sr?phrase={self._url_encode(movie)}"
            else:
                canonical_target = f"https://www.netflix.com/search?q={self._url_encode(movie)}"

        for step in steps:
            tool = step.get("tool")
            args = step.get("args") or {}

            if tool == "app.open_target_in_app":
                target = str(args.get("target") or "").strip()
                app = str(args.get("app") or "chrome").strip() or "chrome"
                if kind in {"shopping", "food_delivery", "groceries"}:
                    target = canonical_target or target
                    app = "chrome"
                    step = {**step, "args": {"target": target, "app": app}}
                key = (tool, target.lower(), app.lower())
                if key in seen_open_targets:
                    continue
                seen_open_targets.add(key)
                deduped.append(step)
                continue

            if tool == "search.query":
                query = self._normalize(str(args.get("query") or ""))
                if not query or query in seen_search_queries:
                    continue
                seen_search_queries.add(query)
                deduped.append(step)
                continue

            deduped.append(step)

        return deduped

    def _execute_vision_step(self, goal: str) -> Tuple[str, str]:
        result = None
        attempts = max(1, self.vision_retry_count)
        for attempt in range(attempts):
            result = self.vision_skill.run_once_result(goal, source="agentic")
            if not self._vision_needs_retry(result):
                break
            if attempt < attempts - 1:
                time.sleep(2.0 + attempt)
        summary = (result.get("summary") or result.get("alert_message") or "No clear visual conclusion.").strip()
        matched = bool(result.get("matched"))
        severity = str(result.get("severity") or "low").strip().lower()
        action_command = str(result.get("action_command") or "").strip()

        parts = [f"Vision matched={'yes' if matched else 'no'} severity={severity}: {summary}"]
        status = "ok" if matched or summary else "failed"

        if result.get("screenshot_path"):
            parts.append(f"screenshot={result.get('screenshot_path')}")

        if result.get("should_act") and action_command:
            action_output, action_status = self._execute_native_action(action_command)
            parts.append(f"action={action_command}")
            parts.append(f"result={action_output}")
            if action_status == "failed":
                status = "failed"

        return " | ".join(parts), status

    def _vision_needs_retry(self, result: Optional[Dict]) -> bool:
        if not result:
            return True
        summary = str(result.get("summary") or "").strip().lower()
        indicators = [
            "not loaded yet",
            "still loading",
            "loading",
            "no product results visible",
            "page is not loaded",
            "spinner",
        ]
        return any(marker in summary for marker in indicators)

    def _execute_native_action(self, command: str) -> Tuple[str, str]:
        normalized = self._normalize(command)
        if not normalized:
            return "Missing action command.", "failed"

        if normalized.startswith(("control ", "computer ", "click ", "scroll ", "type ", "press ", "hotkey ", "move ", "screenshot")):
            resp, _ = self.computer_skill.handle_command(command)
            if resp is None:
                return "Computer action was not handled.", "failed"
            return resp, ("failed" if "failed" in resp.lower() else "ok")

        if normalized.startswith(("open ", "launch ", "start ", "play ", "resume ", "continue ")):
            resp, _ = self.app_skill.handle_command(command)
            if resp is None:
                return "App action was not handled.", "failed"
            lowered = resp.lower()
            return resp, ("failed" if lowered.startswith("failed") or "not handled" in lowered else "ok")

        if normalized.startswith(("search ", "lookup ", "find ")):
            resp, _ = self.searching_skill.handle_query(command)
            if resp is None:
                return "Search action was not handled.", "failed"
            return resp[:500], "ok"

        return "Blocked unsafe or unsupported agentic action.", "failed"

    def _format_response(self, user_input: str, plan: Dict, results: List[Dict[str, str]]) -> str:
        lines = []
        goal = plan.get("goal") or user_input
        lines.append(f"Agentic task: {goal}")
        ok_count = sum(1 for r in results if r.get("status") == "ok")
        lines.append(f"Steps completed: {ok_count}/{len(results)}")
        key_lines = self._compact_result_lines(results)
        if key_lines:
            lines.append("")
            lines.append("What happened:")
            lines.extend(key_lines)

        if self.verbose_output:
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

    def _format_spoken_response(self, user_input: str, plan: Dict, results: List[Dict[str, str]]) -> str:
        kind = self._task_kind(user_input)
        ok_count = sum(1 for r in results if r.get("status") == "ok")
        if kind in {"shopping", "food_delivery", "groceries"}:
            vision = next((r for r in results if r.get("tool") == "vision.inspect"), None)
            if vision:
                text = self._strip_urls(str(vision.get("output") or ""))
                lowered = text.lower()
                if "action=control click" in lowered:
                    if kind == "food_delivery":
                        return "I found a visible restaurant option and selected it."
                    if kind == "groceries":
                        return "I found a visible grocery option and selected it."
                    return "I found a visible product candidate and selected it."
                if "action=control scroll" in lowered:
                    if kind == "food_delivery":
                        return "Food delivery results are open. I inspected the page and scrolled for better options."
                    if kind == "groceries":
                        return "Grocery results are open. I inspected the page and scrolled for better options."
                    return "Shopping results are open. I inspected the page and scrolled for better options."
                if "loading" in lowered or "not loaded" in lowered:
                    if kind == "food_delivery":
                        return "The food delivery page was still loading, so I did not choose a restaurant yet."
                    if kind == "groceries":
                        return "The grocery page was still loading, so I did not choose an item yet."
                    return "The shopping page was still loading, so I did not choose a product yet."
            if kind == "food_delivery":
                return f"Food delivery task is running. I completed {ok_count} steps so far."
            if kind == "groceries":
                return f"Grocery task is running. I completed {ok_count} steps so far."
            return f"Shopping task is running. I completed {ok_count} steps so far."
        if kind == "movie":
            return f"Playback task is running. I completed {ok_count} steps."
        return f"Task executed. I completed {ok_count} steps."

    def _compact_result_lines(self, results: List[Dict[str, str]]) -> List[str]:
        lines: List[str] = []
        for r in results:
            tool = r.get("tool", "")
            output = self._strip_urls(str(r.get("output") or "").replace("\n", " ").strip())
            if not output:
                continue
            if tool == "app.open_target_in_app":
                lines.append(f"- Opened target page: {self._truncate(output, 140)}")
            elif tool == "vision.inspect":
                lines.append(f"- Vision: {self._truncate(output, 220)}")
            elif tool == "computer.command":
                lines.append(f"- Computer action: {self._truncate(output, 160)}")
            elif tool == "search.query" and self.verbose_output:
                lines.append(f"- Search: {self._truncate(output, 160)}")
        return lines[:4]

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

    def _plan_requires_confirmation(self, plan: Dict, user_input: str) -> bool:
        if self.confirm_sensitive_only:
            return self._looks_like_sensitive_task(user_input)
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
        m = re.search(
            r"\b(?:order|buy)\s+(.+?)(?:\s+(?:on|from)\s+(?:amazon|flipkart|swiggy|zomato|blinkit|zepto|instamart|bigbasket)|$)",
            lowered,
            flags=re.IGNORECASE,
        )
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

    def _looks_like_sensitive_task(self, text: str) -> bool:
        normalized = self._normalize(text)
        markers = [
            "pay",
            "payment",
            "place order",
            "checkout",
            "upi",
            "card",
            "credit card",
            "debit card",
            "bank",
            "otp",
            "submit",
            "send email",
            "share",
            "post publicly",
            "transfer",
            "delete",
            "remove permanently",
        ]
        return any(marker in normalized for marker in markers)

    def _normalize(self, text: str) -> str:
        text = (text or "").lower()
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _url_encode(self, text: str) -> str:
        from urllib.parse import quote_plus

        return quote_plus((text or "").strip())

    def _platform_search_url(self, platform: str, query: str) -> str:
        platform = self._normalize_platform_token(platform, "amazon")
        template = self.PLATFORM_SEARCH_URLS.get(platform) or self.PLATFORM_SEARCH_URLS["amazon"]
        return template.format(query=self._url_encode(query))

    def _platform_label(self, platform: str) -> str:
        labels = {
            "amazon": "Amazon",
            "flipkart": "Flipkart",
            "swiggy": "Swiggy",
            "zomato": "Zomato",
            "blinkit": "Blinkit",
            "zepto": "Zepto",
            "instamart": "Instamart",
            "bigbasket": "BigBasket",
            "netflix": "Netflix",
            "prime_video": "Prime Video",
        }
        return labels.get(self._normalize_platform_token(platform, "amazon"), "selected platform")

    def _normalize_platform_token(self, platform: str, fallback: str = "unknown") -> str:
        token = self._normalize(platform).replace(" ", "_")
        aliases = {
            "amazon_in": "amazon",
            "amazon_com": "amazon",
            "prime": "prime_video",
            "prime_video": "prime_video",
            "swiggy_instamart": "instamart",
        }
        token = aliases.get(token, token)
        if token in self.PLATFORM_SEARCH_URLS:
            return token
        return fallback

    def _strip_urls(self, text: str) -> str:
        return re.sub(r"https?://\S+", "", text).strip()

    def _truncate(self, text: str, limit: int) -> str:
        text = (text or "").strip()
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "..."

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
