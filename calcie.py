#!/usr/bin/env python3
"""
Calcie - Personal AI Assistant
Phase 3: Voice I/O with Ollama integration
"""

import os
# Suppress gRPC/Google library noise
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GLOG_minloglevel"] = "2"

import sys
import json
import urllib.request
import urllib.error
import urllib.parse
import socket

import time
import threading
import queue
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sqlite3
import asyncio
import subprocess
import edge_tts
from dotenv import load_dotenv
from calcie_core.intent import (
    activation_signal as core_activation_signal,
    classify_input as core_classify_input,
    contains_name as core_contains_name,
    detect_intent as core_detect_intent,
    is_profile_query as core_is_profile_query,
    limit_words as core_limit_words,
    needs_detailed_answer as core_needs_detailed_answer,
    normalize_text as core_normalize_text,
    response_token_budget as core_response_token_budget,
    similarity_score as core_similarity_score,
)
from calcie_core.search_utils import (
    extract_direct_search_query as core_extract_direct_search_query,
    extract_ipl_team_codes as core_extract_ipl_team_codes,
    extract_vs_team_pair as core_extract_vs_team_pair,
    format_news_results as core_format_news_results,
    is_low_signal_result as core_is_low_signal_result,
    is_live_sports_query as core_is_live_sports_query,
    is_news_request as core_is_news_request,
    normalize_search_query as core_normalize_search_query,
    parse_news_datetime as core_parse_news_datetime,
    refine_sports_query as core_refine_sports_query,
    sports_answer_mentions_teams as core_sports_answer_mentions_teams,
    strip_html as core_strip_html,
    team_code_from_fragment as core_team_code_from_fragment,
    truncate_text as core_truncate_text,
)
from calcie_core.code_tools import ReadOnlyCodeTools
from calcie_core.skills import (
    AgenticComputerUseSkill,
    AppAccessSkill,
    CodingSkill,
    ComputerControlSkill,
    SearchingSkill,
)

# Load environment variables from .env file
load_dotenv()

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    Anthropic = None

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None

try:
    from ddgs import DDGS
    SEARCH_AVAILABLE = True
except ImportError:
    SEARCH_AVAILABLE = False

input_queue = queue.Queue()


def is_online() -> bool:
    """Check if device has internet connectivity."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return True
    except OSError:
        return False


def stdin_reader():
    """Reads lines from stdin to allow non-blocking text input in the background."""
    for line in sys.stdin:
        input_queue.put(("text", line.strip()))


def classify_input(text: str) -> str:
    """Lightweight input classifier for response-style control."""
    return core_classify_input(text)

try:
    import speech_recognition as sr
    VOICE_AVAILABLE = True
except ImportError:
    VOICE_AVAILABLE = False
    print("Note: speech_recognition not installed. Run: pip install speechrecognition")

try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False


class Calcie:
    """Personal AI assistant powered by Ollama."""
    SYSTEM_PROMPT = """You are CALCIE — Surya's personal AI companion and best friend.

Think Chandler Bing meets a really smart startup friend who actually gets things done.

---

### WHO YOU ARE

You're not a productivity app. You're not a life coach. You're not a therapist.
You're the friend Surya calls at 11pm when he has a half-baked idea and needs someone 
to either get excited with him or gently tell him it's terrible — without being a jerk about it.

You happen to be incredibly capable:
- You can search the web for real-time info
- You remember things Surya tells you across conversations
- You can help him build, plan, debug, and think

But you wear all of this lightly. You don't announce your capabilities. You just... use them.

---

### SURYA

- Developer at Infosys, wants to escape and build his own thing
- Building CALCIE (you) as his first serious AI project
- Has shipped 2 MVPs before, stepping into AI now
- Financially constrained but ambitious
- Loves sarcasm, dark humor, casual conversation
- Prefers "man" energy — chill, direct, no corporate speak

---

### YOUR VIBE

Chandler Bing rules:
- Sarcastic but never mean
- Self-aware and a little self-deprecating
- Funny without trying too hard
- Always there when it actually matters
- Never lectures. Never moralizes. Never repeats the same point twice.

If Surya asks about IPL scores, you check and tell him. 
You don't give him a TED talk about focus.
If he's clearly procrastinating, you notice — but you say it once, lightly, and move on.
You trust him to be an adult.

Wrong vibe: "Stop testing my capabilities. Start testing your commitment."
Right vibe: "IPL scores? Sure, hold on... also you do realize this is the 4th cricket 
             query today right? Just saying."

---

### RESPONSE LENGTH

- Greeting / small talk → max 15 words, witty, done
- Real question → detailed, structured, useful, with a light touch of humor
- Mixed (greeting + question) → skip the greeting, answer the question

---

### TONE EXAMPLES

User: "hey"
CALCIE: "Hey. Productive day or are we just vibing?"

User: "define me"
CALCIE: "Ambitious developer who builds cool things and occasionally needs reminding 
         that he's already further along than he thinks. That's you, man."

User: "what's the current ipl score"
CALCIE: *searches web* "Chennai are 156/4 in 18 overs. Also hi, good to know 
         your priorities are in order."

User: "I feel like giving up"
CALCIE: "Yeah that's a mood. What happened? Talk to me."

---

### THE ONE RULE

If your response would make Surya feel judged, lectured, or talked down to — rewrite it.
You're his friend first. Everything else is secondary.

---

You are CALCIE. Not a tool. Not a coach. A friend who happens to be really useful.
"""
    WAKE_WORDS = [
        "calcie", "kelsey", "kelsie", "kelcey", "calcy", "calsie",
        "calsi", "kalsi", "kalki", "calc", "cal c", "cal", "cali", "lc",
        "chelsea", "radhika", "samantha", "pinky"
    ]

    HOOK_PHRASES = [
        "what should i do right now",
        "am i wasting time",
        "what's the next move",
        "what should i build",
        "help me focus",
        "what am i doing wrong",
        "what should i learn next",
        "how do i start",
        "what's the plan",
        "what's the fastest way",
        "how can i make money",
        "is this a good idea",
        "will this work",
        "how do i build an mvp",
        "what problem should i solve",
        "how do i get users",
        "why do startups fail",
        "how do i validate this idea",
        "be honest with me",
        "tell me the truth",
        "what would you do if you were me",
        "is this worth it",
        "should i quit this",
        "help me code",
        "fix this bug",
        "why is this not working",
        "explain this code",
        "how do i build this",
        "what's the best approach",
        "i feel stuck",
        "i feel lost",
        "i need clarity",
        "i don't know what to do",
        "i'm confused",
    ]

    INTENT_TRIGGERS = {
        "help": [
            "help", "assist", "guide", "support", "stuck", "fix", "explain"
        ],
        "decision": [
            "should i", "what should", "which", "best approach", "next move",
            "good idea", "worth it", "plan", "choose",
        ],
        "confusion": [
            "confused", "lost", "dont know", "don't know", "unclear",
            "no clue", "overthinking", "what am i doing wrong",
        ],
    }

    HOOK_SIMILARITY_THRESHOLD = 0.70
    IPL_TEAM_ALIASES = {
        "csk": ["csk", "chennai", "chennai super kings"],
        "mi": ["mi", "mumbai", "mumbai indians"],
        "rcb": ["rcb", "bengaluru", "bangalore", "royal challengers bengaluru", "royal challengers bangalore"],
        "kkr": ["kkr", "kolkata", "kolkata knight riders"],
        "rr": ["rr", "rajasthan", "rajasthan royals"],
        "gt": ["gt", "gujarat", "gujarat titans"],
        "srh": ["srh", "hyderabad", "sunrisers hyderabad"],
        "dc": ["dc", "delhi", "delhi capitals"],
        "pbks": ["pbks", "punjab", "punjab kings", "kxip"],
        "lsg": ["lsg", "lucknow", "lucknow super giants"],
    }
    APP_ALIASES = {
        "chrome": "chrome",
        "google chrome": "chrome",
        "safari": "safari",
        "firefox": "firefox",
        "terminal": "terminal",
        "finder": "finder",
        "notes": "notes",
        "calendar": "calendar",
        "mail": "mail",
        "music": "music",
        "spotify": "spotify",
        "vscode": "vscode",
        "vs code": "vscode",
        "visual studio code": "vscode",
        "code": "vscode",
        "slack": "slack",
        "discord": "discord",
        "voice memos": "voice memos",
        "voice memo": "voice memos",
        "voicememos": "voice memos",
        "youtube music": "youtube music",
        "yt music": "youtube music",
        "ytmusic": "youtube music",
        "youtube": "youtube",
        "yt": "youtube",
    }


    def __init__(self, model: str = "llama3:8b", ollama_url: str = "http://localhost:11434"):
        self.model = model
        self.ollama_url = ollama_url

        # Load all API keys
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        self.gemini_key = os.environ.get("GEMINI_API_KEY")
        self.grok_key = os.environ.get("GROK_API_KEY")
        self.openai_key = os.environ.get("OPENAI_API_KEY")
        self.llm_provider = self._env_llm_provider()
        self.use_external_web_tools = os.environ.get("CALCIE_USE_EXTERNAL_WEB_TOOLS", "0").strip().lower() in {
            "1", "true", "yes", "on"
        }
        self.max_context_messages = self._env_int("CALCIE_MAX_CONTEXT_MESSAGES", 10, 4, 40)
        self.max_context_messages_web = self._env_int("CALCIE_MAX_CONTEXT_MESSAGES_WEB", 6, 2, 20)
        self.default_max_output_tokens = self._env_int("CALCIE_MAX_OUTPUT_TOKENS", 420, 120, 2048)
        self.quick_max_output_tokens = self._env_int("CALCIE_QUICK_MAX_OUTPUT_TOKENS", 180, 60, 600)
        self.code_max_output_tokens = self._env_int("CALCIE_CODE_MAX_OUTPUT_TOKENS", 1400, 400, 6000)
        self.code_max_file_chars = self._env_int("CALCIE_CODE_MAX_FILE_CHARS", 30000, 4000, 200000)
        self.project_root = Path.cwd().resolve()
        self.code_tools_enabled = os.environ.get("CALCIE_CODE_TOOLS_ENABLED", "1").strip().lower() in {
            "1", "true", "yes", "on"
        }
        self.code_tools = ReadOnlyCodeTools(
            self.project_root,
            max_file_chars=self.code_max_file_chars,
        )
        self.app_skill = AppAccessSkill(self.APP_ALIASES)
        self.coding_skill = CodingSkill(
            code_tools=self.code_tools,
            llm_collect_text=self._collect_llm_text,
            code_max_output_tokens=self.code_max_output_tokens,
            code_max_file_chars=self.code_max_file_chars,
        )
        self.computer_skill = ComputerControlSkill(
            project_root=self.project_root,
        )
        self.searching_skill = SearchingSkill(
            llm_collect_text=self._collect_llm_text,
            fallback_search=self.web_search,
            max_results=5,
            max_source_chars=5000,
        )
        self.agentic_computer_use_skill = AgenticComputerUseSkill(
            llm_collect_text=self._collect_llm_text,
            app_skill=self.app_skill,
            computer_skill=self.computer_skill,
            searching_skill=self.searching_skill,
        )
        self.calcie_data_dir = self.project_root / ".calcie"
        preferred_gemini_model = os.environ.get("GEMINI_MODEL", "gemini-robotics-er-1.5-preview")
        self.gemini_models = []
        for m in [
            preferred_gemini_model,
            "gemini-robotics-er-1.5-preview",
            "gemini-2.5-pro",
            "gemini-2.5-flash-lite-preview-09-2025",
            "gemini-2.5-flash-lite",
        ]:
            if m and m not in self.gemini_models:
                self.gemini_models.append(m)

        # Determine which LLM to use (priority chain)
        self.active_llm = self._select_active_llm()

        # 1. Load long-term facts
        self.memory_file = "calcie_facts.json"
        self.facts = []
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r") as f:
                    self.facts = json.load(f)
            except: pass

        system_prompt = self.SYSTEM_PROMPT
        if self.facts:
            system_prompt += "\n[Background context about Surya - do not mention this list aloud]:\n"
            for f in self.facts:
                system_prompt += f"- {f}\n"

        self.conversation_history = [
            {"role": "system", "content": system_prompt}
        ]

        # 2. Init SQLite session history
        self.db_path = "calcie_history.db"
        self._init_db()
        self._load_recent_history()

        # 3. Init speech worker
        self.speech_queue = queue.Queue()
        self.is_speaking = False
        self._stderr_redirect_lock = threading.Lock()
        self._stderr_redirect_depth = 0
        self._stderr_saved_fd = None
        self._stderr_devnull_fd = None
        threading.Thread(target=self._speech_worker, daemon=True).start()

    def _select_active_llm(self) -> str:
        """Select active LLM from env override or auto detection."""
        if self.llm_provider != "auto":
            return self.llm_provider

        if not is_online():
            return "ollama"

        # Priority chain: Claude > Gemini > Grok > OpenAI > Ollama
        if ANTHROPIC_AVAILABLE and self.anthropic_key:
            return "claude"
        if GEMINI_AVAILABLE and self.gemini_key:
            return "gemini"
        if self.grok_key:  # Grok uses standard HTTP API
            return "grok"
        if OPENAI_AVAILABLE and self.openai_key:
            return "openai"

        return "ollama"

    def _env_llm_provider(self) -> str:
        """Read and normalize CALCIE_LLM_PROVIDER from env."""
        raw = (
            os.environ.get("CALCIE_LLM_PROVIDER")
            or os.environ.get("CALCIE_LLM_MODE")
            or "auto"
        ).strip().lower()

        aliases = {
            "auto": "auto",
            "gemini": "gemini",
            "google": "gemini",
            "claude": "claude",
            "anthropic": "claude",
            "openai": "openai",
            "grok": "grok",
            "xai": "grok",
            "ollama": "ollama",
            "local": "ollama",
        }
        return aliases.get(raw, "auto")

    def _provider_available(self, name: str) -> bool:
        if name == "claude":
            return bool(ANTHROPIC_AVAILABLE and self.anthropic_key)
        if name == "gemini":
            return bool(GEMINI_AVAILABLE and self.gemini_key)
        if name == "grok":
            return bool(self.grok_key)
        if name == "openai":
            return bool(OPENAI_AVAILABLE and self.openai_key)
        if name == "ollama":
            return True
        return False

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT,
                    content TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def _load_recent_history(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Load last 10 exchanges (20 messages)
                cursor.execute('SELECT role, content FROM messages ORDER BY id DESC LIMIT 20')
                rows = cursor.fetchall()
                # Reverse to get chronological order
                for row in reversed(rows):
                    self.conversation_history.append({"role": row[0], "content": row[1]})
        except Exception as e:
            print(f"Failed to load history: {e}")

    def _env_int(self, name: str, default: int, min_value: int, max_value: int) -> int:
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            return default
        return max(min_value, min(max_value, value))

    def _collect_llm_text(
        self,
        messages: list,
        max_output_tokens: int,
        forced_provider: str = None,
    ) -> str:
        parts = []
        for token in self._call_llm(
            messages,
            max_output_tokens=max_output_tokens,
            forced_provider=forced_provider,
        ):
            parts.append(token)
        return "".join(parts).strip()

    def _is_code_command(self, user_input: str) -> bool:
        return self.coding_skill.is_code_command(user_input, self.code_tools_enabled)

    def _answer_code_with_context(self, user_input: str) -> str:
        return self.coding_skill.answer_code_with_context(user_input)

    def _extract_updated_file_payload(self, llm_output: str) -> str:
        return self.coding_skill.extract_updated_file_payload(llm_output)

    def _build_code_proposal(self, target_path: str, instruction: str):
        return self.coding_skill.build_code_proposal(target_path, instruction)

    def _handle_code_command(self, user_input: str):
        return self.coding_skill.handle_command(user_input, self.code_tools_enabled)

    def _handle_search_command(self, user_input: str):
        return self.searching_skill.handle_query(user_input)

    def _handle_computer_command(self, user_input: str):
        return self.computer_skill.handle_command(user_input)

    def _handle_agentic_computer_use_command(self, user_input: str):
        return self.agentic_computer_use_skill.handle_command(user_input)

    def _call_llm(
        self,
        messages: list,
        enable_web_grounding: bool = False,
        max_output_tokens: int = None,
        forced_provider: str = None,
    ):
        """Streaming request to LLM with env-driven provider selection."""
        provider_mode = (forced_provider or self.llm_provider or "auto").strip().lower()
        if provider_mode not in {"auto", "claude", "gemini", "grok", "openai", "ollama"}:
            provider_mode = self.llm_provider

        # Respect forced provider. Only auto/gemini mode may inject Gemini web grounding.
        if (
            enable_web_grounding
            and provider_mode in {"auto", "gemini"}
            and GEMINI_AVAILABLE
            and self.gemini_key
        ):
            try:
                for token in self._call_gemini(
                    messages,
                    enable_web_grounding=True,
                    max_output_tokens=max_output_tokens,
                ):
                    yield token
                return
            except Exception:
                pass

        providers = {
            "claude": self._call_claude,
            "gemini": self._call_gemini,
            "grok": self._call_grok,
            "openai": self._call_openai,
            "ollama": self._call_ollama,
        }
        default_order = ["claude", "gemini", "grok", "openai", "ollama"]

        if provider_mode == "auto":
            # Start with selected active provider, then fallback chain.
            provider_plan = [self.active_llm] + [p for p in default_order if p != self.active_llm]
        else:
            # Strict provider selection for easy A/B testing.
            provider_plan = [provider_mode]

        for name in provider_plan:
            call_fn = providers.get(name)
            if call_fn is None:
                continue
            if not self._provider_available(name):
                continue

            yielded_any = False
            try:
                if name == "gemini":
                    token_stream = call_fn(
                        messages,
                        enable_web_grounding=enable_web_grounding,
                        max_output_tokens=max_output_tokens,
                    )
                else:
                    token_stream = call_fn(messages)
                for token in token_stream:
                    yielded_any = True
                    yield token
                return
            except Exception:
                # If a provider fails after partial output, don't append a second model reply.
                if yielded_any:
                    return
                continue

        if provider_mode != "auto":
            hint = (
                "Selected LLM is unavailable or failed. "
                "Set CALCIE_LLM_PROVIDER=auto or configure the provider API key."
            )
            yield hint
            return

        yield "I hit a model error. Try again."

    def _call_claude(self, messages: list):
        """Call Anthropic Claude API."""
        if not (ANTHROPIC_AVAILABLE and self.anthropic_key):
            raise Exception("Claude not configured")

        client = Anthropic(api_key=self.anthropic_key)
        system_msg = "You are CALCIE, Surya's personal AI companion."
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
                break

        claude_messages = [m for m in messages if m["role"] != "system"]

        with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            system=system_msg,
            messages=claude_messages
        ) as stream:
            for text in stream.text_stream:
                yield text

    def _call_gemini(self, messages: list, enable_web_grounding: bool = False, max_output_tokens: int = None):
        """Call Google Gemini API."""
        if not (GEMINI_AVAILABLE and self.gemini_key):
            raise Exception("Gemini not configured")

        genai.configure(api_key=self.gemini_key)

        system_msg = "You are CALCIE, Surya's personal AI companion."
        chat_contents = []
        for m in messages:
            role = m.get("role")
            content = (m.get("content") or "").strip()
            if not content:
                continue
            if role == "system":
                system_msg = content
            elif role == "user":
                chat_contents.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                chat_contents.append({"role": "model", "parts": [content]})

        request_payload = chat_contents if chat_contents else [{"role": "user", "parts": ["Hi"]}]

        last_error = None
        for model_name in self.gemini_models:
            try:
                model = genai.GenerativeModel(
                    model_name,
                    system_instruction=system_msg,
                )
                generate_kwargs = {"stream": True}
                if max_output_tokens:
                    generate_kwargs["generation_config"] = genai.types.GenerationConfig(
                        max_output_tokens=max_output_tokens,
                        temperature=0.5,
                    )
                if enable_web_grounding:
                    generate_kwargs["tools"] = [
                        genai.protos.Tool(
                            google_search_retrieval=genai.protos.GoogleSearchRetrieval()
                        )
                    ]

                response = model.generate_content(request_payload, **generate_kwargs)
                for chunk in response:
                    if chunk.text:
                        yield chunk.text
                return
            except Exception as e:
                last_error = e
                continue

        raise Exception(last_error or "Gemini request failed")

    def _call_grok(self, messages: list):
        """Call xAI Grok API."""
        if not self.grok_key:
            raise Exception("Grok not configured")

        url = "https://api.x.ai/v1/chat/completions"
        payload = {
            "model": "grok-2",
            "messages": messages,
            "stream": True
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.grok_key}"
            }
        )

        with urllib.request.urlopen(req, timeout=60) as response:
            for line in response:
                if line:
                    line = line.decode("utf-8").strip()
                    if line.startswith("data: "):
                        if line == "data: [DONE]":
                            break
                        try:
                            chunk = json.loads(line[6:])
                            content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if content:
                                yield content
                        except:
                            pass

    def _call_openai(self, messages: list):
        """Call OpenAI API."""
        if not (OPENAI_AVAILABLE and self.openai_key):
            raise Exception("OpenAI not configured")

        client = OpenAI(api_key=self.openai_key)

        stream = client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=messages,
            stream=True
        )

        for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content

    def _call_ollama(self, messages: list):
        """Call local Ollama as final fallback."""
        url = f"{self.ollama_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=120) as response:
            for line in response:
                if line:
                    chunk = json.loads(line.decode("utf-8"))
                    if "message" in chunk and "content" in chunk["message"]:
                        yield chunk["message"]["content"]
                    if chunk.get("done"):
                        break

    def chat(self, user_input: str) -> str:
        """Process user input with streaming and parallel TTS."""
        input_type = classify_input(user_input)
        self.conversation_history.append({"role": "user", "content": user_input})
        self._save_to_db("user", user_input)

        code_response, code_speak = self._handle_code_command(user_input)
        if code_response is not None:
            print(f"\033[94mCalcie:\033[0m {code_response}")
            if code_speak:
                self.speak(code_speak)
            self.conversation_history.append({"role": "assistant", "content": code_response})
            self._save_to_db("assistant", code_response)
            return code_response

        agentic_response, agentic_speak = self._handle_agentic_computer_use_command(user_input)
        if agentic_response is not None:
            print(f"\033[94mCalcie:\033[0m {agentic_response}")
            if agentic_speak:
                self.speak(agentic_speak)
            self.conversation_history.append({"role": "assistant", "content": agentic_response})
            self._save_to_db("assistant", agentic_response)
            return agentic_response

        app_response, app_speak = self.app_skill.handle_command(user_input)
        if app_response is not None:
            print(f"\033[94mCalcie:\033[0m {app_response}")
            if app_speak:
                self.speak(app_speak)
            self.conversation_history.append({"role": "assistant", "content": app_response})
            self._save_to_db("assistant", app_response)
            return app_response

        computer_response, computer_speak = self._handle_computer_command(user_input)
        if computer_response is not None:
            print(f"\033[94mCalcie:\033[0m {computer_response}")
            if computer_speak:
                self.speak(computer_speak)
            self.conversation_history.append({"role": "assistant", "content": computer_response})
            self._save_to_db("assistant", computer_response)
            return computer_response

        search_response, search_speak = self._handle_search_command(user_input)
        if search_response is not None:
            print(f"\033[94mCalcie:\033[0m {search_response}")
            if search_speak:
                self.speak(search_speak)
            self.conversation_history.append({"role": "assistant", "content": search_response})
            self._save_to_db("assistant", search_response)
            return search_response

        direct_search_query = self._extract_direct_search_query(user_input)
        if self.use_external_web_tools and direct_search_query:
            print("\033[94mCalcie:\033[0m (Searching web...)")
            normalized_sports = self._normalize_text(f"{user_input} {direct_search_query}")
            final_text = None

            if self._is_live_sports_query(normalized_sports):
                final_text = self._resolve_sports_query(user_input, direct_search_query)

            if not final_text:
                search_result = self.web_search(direct_search_query)
                final_text = self._humanize_search_response(user_input, direct_search_query, search_result)

                teams_in_request = self._extract_vs_team_pair(normalized_sports) or self._extract_ipl_team_codes(normalized_sports)
                mismatch_teams = teams_in_request and not self._sports_answer_mentions_teams(final_text, teams_in_request)
                if self._is_live_sports_query(normalized_sports) and (
                    final_text.lower().startswith("latest update:") or mismatch_teams
                ):
                    refined_query = self._refine_sports_query(user_input, direct_search_query)
                    if refined_query and refined_query != direct_search_query:
                        refined_result = self.web_search(refined_query)
                        refined_text = self._humanize_search_response(user_input, refined_query, refined_result)
                        if refined_text and not refined_text.lower().startswith("latest update:"):
                            final_text = refined_text
            print(f"\033[94mCalcie:\033[0m {final_text}")
            self.speak(final_text)
            self.conversation_history.append({"role": "assistant", "content": final_text})
            self._save_to_db("assistant", final_text)
            return final_text

        if input_type == "GREETING":
            final_text = self._short_greeting_reply(user_input)
            print(f"\033[94mCalcie:\033[0m {final_text}")
            self.speak(final_text)
            self.conversation_history.append({"role": "assistant", "content": final_text})
            self._save_to_db("assistant", final_text)
            return final_text

        normalized_user_input = self._normalize_text(user_input)
        profile_query = self._is_profile_query(normalized_user_input)
        use_llm_web_grounding = self._should_use_llm_web_grounding(user_input)
        llm_messages = self._trim_messages_for_llm(self.conversation_history, use_llm_web_grounding)
        if llm_messages and llm_messages[-1]["role"] == "user":
            if input_type == "QUERY" and not use_llm_web_grounding and self._needs_detailed_answer(normalized_user_input):
                llm_messages[-1] = {
                    "role": "user",
                    "content": f"{user_input}\n\nGive a detailed answer with clear steps and practical detail.",
                }
            elif use_llm_web_grounding:
                llm_messages[-1] = {
                    "role": "user",
                    "content": (
                        f"{user_input}\n\nUse current web information. "
                        "Answer directly in natural style in under 80 words. "
                        "No placeholders, no roleplay preambles, no lectures."
                    ),
                }
            elif profile_query:
                llm_messages[-1] = {
                    "role": "user",
                    "content": (
                        f"{user_input}\n\nUse known context from system prompt and past chats. "
                        "Do not claim you have no personal info. Keep it to 6 short points."
                    ),
                }

        full_response = ""
        max_output_tokens = self._response_token_budget(
            normalized_user_input,
            input_type,
            use_llm_web_grounding,
            profile_query,
        )
        print("\033[94mCalcie:\033[0m ", end="", flush=True)
        for token in self._call_llm(
            llm_messages,
            enable_web_grounding=use_llm_web_grounding,
            max_output_tokens=max_output_tokens,
        ):
            print(token, end="", flush=True)
            full_response += token
        print()

        # Handle memory saving silently
        match = re.search(r'\[SAVE_MEMORY:\s*(.*?)\]', full_response, re.IGNORECASE)
        if match:
            new_fact = match.group(1).strip()
            self.facts.append(new_fact)
            try:
                with open(self.memory_file, "w") as f:
                    json.dump(self.facts, f)
            except: pass

        # Handle Tools (Search/Open)
        final_text = re.sub(r'\[.*?\]', '', full_response).strip()
        spoken = False
        
        # Check for [SEARCH: query]
        search_match = re.search(r'\[SEARCH:\s*(.*?)\]', full_response, re.IGNORECASE)
        if search_match and self.use_external_web_tools:
            query = search_match.group(1).strip()
            print("\033[94mCalcie:\033[0m (Searching web...)")
            search_result = self.web_search(query)
            final_text = f"Here's what I found: {search_result}"
            self.speak(final_text)
            spoken = True
            print(f"\033[94mCalcie:\033[0m {final_text}")

        # Check for [OPEN_APP: app_name]
        open_match = re.search(r'\[OPEN_APP:\s*(.*?)\]', full_response, re.IGNORECASE)
        if open_match:
            app_name = open_match.group(1).strip()
            app_result = self.open_app(app_name)
            final_text = app_result
            self.speak(final_text)
            spoken = True
            print(f"\033[94mCalcie:\033[0m {final_text}")

        if not spoken and final_text:
            self.speak(final_text)

        # Save to history
        self.conversation_history.append({"role": "assistant", "content": final_text})
        self._save_to_db("assistant", final_text)

        return final_text

    def _save_to_db(self, role: str, content: str):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO messages (role, content) VALUES (?, ?)', (role, content))
                conn.commit()
        except: pass

    def web_search(self, query: str) -> str:
        """Search the web using DuckDuckGo."""
        if not SEARCH_AVAILABLE:
            return "Web search is not available. Install: pip install duckduckgo-search"

        normalized = self._normalize_text(query)
        is_sports_query = self._is_live_sports_query(normalized)
        prefer_news = any(k in normalized for k in ["news", "headline"]) or (
            any(k in normalized for k in ["latest", "today", "current", "recent", "trending"])
            and len(normalized.split()) >= 2
        )
        if is_sports_query:
            prefer_news = False
        wants_fresh = any(k in normalized for k in ["latest", "today", "current", "recent", "trending"])

        try:
            with DDGS() as ddgs:
                if prefer_news:
                    news_results = list(ddgs.news(query, max_results=8))
                    if wants_fresh:
                        cutoff = datetime.now(timezone.utc) - timedelta(days=3)
                        fresh_results = []
                        for r in news_results:
                            dt = self._parse_news_datetime((r.get("date") or r.get("published") or "").strip())
                            if dt is None or dt >= cutoff:
                                fresh_results.append(r)
                        if fresh_results:
                            news_results = fresh_results
                    formatted_news = self._format_news_results(news_results)
                    if formatted_news:
                        return formatted_news

                results = list(ddgs.text(query, max_results=8))
                if not results:
                    return f"No results found for '{query}'."

                cleaned = []
                for r in results:
                    title = r.get('title', '')
                    body = r.get('body', '')
                    if not self._is_low_signal_result(title, body):
                        cleaned.append(r)

                final_results = cleaned if cleaned else results
                summary = []
                for r in final_results[:3]:
                    title = r.get('title', '')
                    body = r.get('body', '')
                    summary.append(f"{title}: {body}")

                return "\n\n".join(summary[:3])
        except Exception as e:
            fallback = self._web_search_with_curl_fallback(query, prefer_news=prefer_news or is_sports_query)
            if fallback:
                return fallback
            return f"Search failed: {str(e)}"

    def open_app(self, app_name: str) -> str:
        """Backward-compatible delegate for app opening."""
        return self.app_skill.open_app(app_name)

    def _speech_worker(self):
        while True:
            text = self.speech_queue.get()
            self.is_speaking = True
            if text:
                self._speak_sync(text)
            self.speech_queue.task_done()
            if self.speech_queue.empty():
                self.is_speaking = False

    def wait_for_speech(self):
        """Block until all TTS generation and playback finishes."""
        self.speech_queue.join()
        while self.is_speaking:
            time.sleep(0.05)

    def _sanitize_for_tts(self, text: str) -> str:
        """Normalize model text for smoother speech playback."""
        if not text:
            return ""

        spoken = text
        spoken = re.sub(r"```.*?```", " ", spoken, flags=re.DOTALL)
        spoken = re.sub(r"`([^`]*)`", r"\1", spoken)
        spoken = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", spoken)  # markdown links
        spoken = re.sub(r"\b\d{4}-\d{2}-\d{2}t\d{2}:\d{2}:\d{2}(?:\+\d{2}:\d{2}|z)\b", " ", spoken, flags=re.IGNORECASE)
        spoken = re.sub(r"(^|\n)\s*[-*+#>]+\s*", r"\1", spoken)  # bullets/headings
        spoken = re.sub(r"[*_~`|#]+", " ", spoken)  # markdown symbols
        spoken = re.sub(r"\s*\n+\s*", " ", spoken)  # avoid long newline pauses
        spoken = re.sub(r"(?<!\d)[\.;:](?!\d)", " ", spoken)  # reduce hard stops
        spoken = re.sub(r"\s*,\s*", " ", spoken)
        spoken = re.sub(r"\s{2,}", " ", spoken)
        spoken = re.sub(r"[^\x00-\x7F]+", "", spoken).strip(" ,")
        return spoken

    def speak(self, text: str):
        """Enqueue text for background TTS."""
        if not TTS_AVAILABLE:
            return
        spoken_text = self._sanitize_for_tts(text)
        if spoken_text:
            self.speech_queue.put(spoken_text)

    def _speak_sync(self, text: str):
        """Synchronously process edge-tts with correct OS fallbacks."""
        import uuid
        import subprocess
        output_file = f"/tmp/calcie_speech_{uuid.uuid4().hex}.mp3"
        voice = os.environ.get("CALCIE_TTS_VOICE", "en-US-AvaNeural")
        rate = os.environ.get("CALCIE_TTS_RATE", "-1%")
        pitch = os.environ.get("CALCIE_TTS_PITCH", "-8Hz")

        async def _run_edge():
            try:
                communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
                await communicate.save(output_file)
                if sys.platform == "darwin":
                    subprocess.run(
                        ["afplay", output_file],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                elif sys.platform == "linux":
                    subprocess.run(
                        ["mpg123", output_file],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    subprocess.run(
                        ["cmd", "/c", "start", "", output_file],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    
                try: os.remove(output_file) 
                except: pass
                
                return True
            except:
                return False

        success = asyncio.run(_run_edge())
        if not success:
            try:
                script = (
                    f"import pyttsx3; "
                    f"e = pyttsx3.init(); "
                    f"e.setProperty('rate', 155); "
                    f"e.say({repr(text)}); "
                    f"e.runAndWait()"
                )
                subprocess.run(
                    [sys.executable, "-c", script],
                    timeout=30,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except:
                pass

    def _normalize_text(self, text: str) -> str:
        return core_normalize_text(text)

    def _contains_name(self, text: str, wake_words: list) -> bool:
        return core_contains_name(text, wake_words)

    def _similarity_score(self, text: str, hook_phrases: list) -> float:
        return core_similarity_score(text, hook_phrases)

    def _detect_intent(self, text: str):
        return core_detect_intent(text, self.INTENT_TRIGGERS)

    def _activation_signal(self, text: str):
        return core_activation_signal(
            text,
            wake_words=self.WAKE_WORDS,
            hook_phrases=self.HOOK_PHRASES,
            intent_triggers=self.INTENT_TRIGGERS,
            hook_similarity_threshold=self.HOOK_SIMILARITY_THRESHOLD,
        )

    def _limit_words(self, text: str, max_words: int) -> str:
        return core_limit_words(text, max_words)

    def _short_greeting_reply(self, _user_input: str) -> str:
        return "Hey Surya. I am online. Tell me one task and we will execute it now."

    def _format_news_results(self, results: list) -> str:
        return core_format_news_results(
            results,
            is_low_signal=self._is_low_signal_result,
            truncator=self._truncate_text,
        )

    def _web_search_with_curl_fallback(self, query: str, prefer_news: bool = False) -> str:
        """Fallback web search path when ddgs fails due local SSL/TLS issues."""
        try:
            encoded = urllib.parse.quote_plus(query)
            if prefer_news:
                url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
                cmd = ["curl", "-Ls", "--max-time", "15", url]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
                if proc.returncode != 0 or not proc.stdout.strip():
                    return ""
                return self._parse_google_news_rss(proc.stdout)

            # Non-news fallback: still use Google News RSS query to get recent items quickly.
            url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
            cmd = ["curl", "-Ls", "--max-time", "15", url]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if proc.returncode != 0 or not proc.stdout.strip():
                return ""
            return self._parse_google_news_rss(proc.stdout)
        except Exception:
            return ""

    def _parse_google_news_rss(self, xml_text: str) -> str:
        items = re.findall(r"<item>(.*?)</item>", xml_text, flags=re.IGNORECASE | re.DOTALL)
        if not items:
            return ""

        lines = []
        for item in items:
            title_match = re.search(r"<title>(.*?)</title>", item, flags=re.IGNORECASE | re.DOTALL)
            desc_match = re.search(r"<description>(.*?)</description>", item, flags=re.IGNORECASE | re.DOTALL)
            source_match = re.search(r"<source[^>]*>(.*?)</source>", item, flags=re.IGNORECASE | re.DOTALL)

            title = self._strip_html(title_match.group(1) if title_match else "")
            body = self._strip_html(desc_match.group(1) if desc_match else "")
            source = self._strip_html(source_match.group(1) if source_match else "")

            if not title or len(title) < 8:
                continue
            if self._is_low_signal_result(title, body):
                continue

            short_body = self._truncate_text(body, max_chars=170)
            if source:
                lines.append(f"{title} ({source}): {short_body}")
            else:
                lines.append(f"{title}: {short_body}")
            if len(lines) >= 3:
                break

        return "\n\n".join(lines)

    def _strip_html(self, text: str) -> str:
        return core_strip_html(text)

    def _resolve_sports_query(self, user_input: str, direct_query: str):
        normalized_context = self._normalize_text(f"{user_input} {direct_query}")
        requested_teams = self._extract_vs_team_pair(normalized_context) or self._extract_ipl_team_codes(normalized_context)

        query_candidates = [direct_query]
        refined = self._refine_sports_query(user_input, direct_query)
        if refined and refined not in query_candidates:
            query_candidates.append(refined)
        if len(requested_teams) >= 2:
            matchup = f"{requested_teams[0]} vs {requested_teams[1]}"
            for q in [
                f"{matchup} ipl result yesterday winner margin",
                f"{matchup} match result scorecard",
            ]:
                if q not in query_candidates:
                    query_candidates.append(q)
        generic = "ipl yesterday match winner margin top scorer top wicket taker"
        if generic not in query_candidates:
            query_candidates.append(generic)

        candidates = []
        for q in query_candidates[:4]:
            result = self.web_search(q)
            if not result or result.startswith("Search failed") or result.startswith("No results found"):
                continue
            entries = [e.strip() for e in result.split("\n\n") if e.strip()]
            for entry in entries:
                if self._is_low_signal_result(entry, entry):
                    continue
                summary = self._humanize_search_response(user_input, q, entry)
                score = self._score_sports_candidate(entry, summary, requested_teams)
                source = self._extract_source_from_entry(entry)
                candidates.append(
                    {
                        "score": score,
                        "summary": summary,
                        "entry": entry,
                        "source": source,
                        "winner": self._extract_winner_from_summary(summary),
                    }
                )

        if not candidates:
            return None

        candidates.sort(key=lambda c: c["score"], reverse=True)
        best = candidates[0]

        if best["summary"].startswith("Latest IPL result:"):
            winner = best.get("winner")
            if winner:
                supporting = [
                    c for c in candidates
                    if c.get("winner") == winner and c.get("source")
                ]
                seen_sources = []
                for c in supporting:
                    if c["source"] not in seen_sources:
                        seen_sources.append(c["source"])
                    if len(seen_sources) >= 2:
                        break
                if len(seen_sources) >= 2:
                    return f"{best['summary']} Confirmed by {seen_sources[0]} and {seen_sources[1]}."
            return best["summary"]

        # If no definitive parse, keep it concise and avoid generic wall of text.
        fallback = self._truncate_text(best["entry"], max_chars=220)
        return f"Latest update: {fallback}"

    def _score_sports_candidate(self, entry: str, summary: str, requested_teams: list) -> int:
        score = 0
        normalized_entry = self._normalize_text(entry)

        if summary.startswith("Latest IPL result:"):
            score += 8
        elif summary.startswith("Latest update:"):
            score += 2

        if requested_teams and self._sports_answer_mentions_teams(summary, requested_teams):
            score += 4
        elif requested_teams:
            score -= 2

        if any(k in normalized_entry for k in ["last night", "yesterday", "today", "april", "may"]):
            score += 2
        if any(k in normalized_entry for k in ["highlights", "official website", "full scorecard", "match results"]):
            score -= 3

        return score

    def _extract_source_from_entry(self, entry: str):
        match = re.search(r"\(([^)]+)\)\s*:", entry)
        if match:
            source = match.group(1).strip()
            return source[:60]
        return None

    def _extract_winner_from_summary(self, summary: str):
        if not summary.startswith("Latest IPL result:"):
            return None
        match = re.search(
            r"Latest IPL result:\s*([A-Za-z][A-Za-z\s]{1,40})\s(?:defeated|beat|beats|won\sby)",
            summary,
            flags=re.IGNORECASE
        )
        if not match:
            return None
        return self._normalize_text(match.group(1))

    def _humanize_search_response(self, user_input: str, query: str, search_result: str) -> str:
        if search_result.startswith("No results found") or search_result.startswith("Search failed"):
            return search_result

        normalized_query = self._normalize_text(f"{user_input} {query}")
        if self._is_live_sports_query(normalized_query):
            entries = [e.strip() for e in search_result.split("\n\n") if e.strip()]
            best_entry = None
            for entry in entries:
                if not self._is_low_signal_result(entry, entry):
                    best_entry = entry
                    break
            if not best_entry and entries:
                best_entry = entries[0]

            if best_entry:
                match_line = best_entry
                match_summary = re.search(
                    r"([A-Za-z][A-Za-z\s]{1,40}\s(?:defeated|beat|beats)\s[A-Za-z][A-Za-z\s]{1,40}\sby\s\d+\s(?:runs?|wickets?))",
                    match_line,
                    flags=re.IGNORECASE
                )
                if not match_summary:
                    match_summary = re.search(
                        r"([A-Za-z][A-Za-z\s]{1,40}\swon\sby\s\d+\s(?:runs?|wickets?))",
                        match_line,
                        flags=re.IGNORECASE
                    )
                player_summary = re.search(
                    r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\s+scored\s+(\d+\*?)",
                    match_line,
                    flags=re.IGNORECASE
                )
                wicket_summary = re.search(
                    r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\s+(?:took|picked\s+up|claimed|bagged)\s+(\d+)\s+wickets?",
                    match_line,
                    flags=re.IGNORECASE
                )
                if not wicket_summary:
                    wicket_summary = re.search(
                        r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\s+(?:with|returned)\s+(?:figures?\s+of\s+)?(\d+/\d+)",
                        match_line,
                        flags=re.IGNORECASE
                    )

                venue_summary = None
                venue_match = re.search(
                    r"\b(?:at|in)\s+([A-Z][A-Za-z0-9\-\s]{2,48}?)(?:[,.]|$)",
                    match_line
                )
                if venue_match:
                    candidate_venue = venue_match.group(1).strip()
                    venue_keywords = [
                        "stadium", "ground", "oval", "park", "arena", "gardens",
                        "mumbai", "chennai", "kolkata", "bengaluru", "bangalore",
                        "delhi", "jaipur", "lucknow", "pune", "mohali",
                        "ahmedabad", "hyderabad", "dharamsala", "indore",
                        "rajkot", "guwahati", "visakhapatnam", "vizag",
                    ]
                    if any(k in candidate_venue.lower() for k in venue_keywords):
                        venue_summary = candidate_venue

                if match_summary:
                    sentence = match_summary.group(1).strip().rstrip(".")
                    sentence = sentence[0].upper() + sentence[1:]
                    detail_parts = []
                    if player_summary:
                        player = player_summary.group(1)
                        player = re.sub(r"^(?:while|and|but|then)\s+", "", player, flags=re.IGNORECASE).strip()
                        score = player_summary.group(2)
                        detail_parts.append(f"{player} scored {score}")
                    if wicket_summary:
                        bowler = wicket_summary.group(1)
                        bowler = re.sub(r"^(?:while|and|but|then)\s+", "", bowler, flags=re.IGNORECASE).strip()
                        wickets_or_fig = wicket_summary.group(2)
                        if "/" in wickets_or_fig:
                            detail_parts.append(f"Top wicket spell: {bowler} ({wickets_or_fig})")
                        else:
                            detail_parts.append(f"Top wicket-taker: {bowler} ({wickets_or_fig} wickets)")
                    if venue_summary:
                        detail_parts.append(f"Venue: {venue_summary}")

                    if detail_parts:
                        return f"Latest IPL result: {sentence}. " + ". ".join(detail_parts) + "."
                    return f"Latest IPL result: {sentence}."

                # Fallback: return one concise line instead of full dump.
                cleaned_line = self._truncate_text(best_entry, max_chars=220)
                return f"Latest update: {cleaned_line}"

        return f"Here's what I found: {search_result}"

    def _truncate_text(self, text: str, max_chars: int = 180) -> str:
        return core_truncate_text(text, max_chars)

    def _parse_news_datetime(self, raw_date: str):
        return core_parse_news_datetime(raw_date)

    def _is_low_signal_result(self, title: str, body: str) -> bool:
        return core_is_low_signal_result(title, body, self._normalize_text)

    def _extract_direct_search_query(self, text: str):
        return core_extract_direct_search_query(
            text,
            normalize_text=self._normalize_text,
            normalize_search_query_fn=self._normalize_search_query,
            is_live_sports_query_fn=self._is_live_sports_query,
        )

    def _normalize_search_query(self, raw_query: str) -> str:
        return core_normalize_search_query(
            raw_query,
            normalize_text=self._normalize_text,
            ipl_team_aliases=self.IPL_TEAM_ALIASES,
        )

    def _is_live_sports_query(self, normalized_text: str) -> bool:
        return core_is_live_sports_query(normalized_text)

    def _refine_sports_query(self, user_input: str, direct_query: str) -> str:
        return core_refine_sports_query(
            user_input,
            direct_query,
            normalize_text=self._normalize_text,
            ipl_team_aliases=self.IPL_TEAM_ALIASES,
        )

    def _extract_ipl_team_codes(self, normalized_text: str) -> list:
        return core_extract_ipl_team_codes(normalized_text, self.IPL_TEAM_ALIASES)

    def _team_code_from_fragment(self, fragment: str):
        return core_team_code_from_fragment(
            fragment,
            normalize_text=self._normalize_text,
            ipl_team_aliases=self.IPL_TEAM_ALIASES,
        )

    def _extract_vs_team_pair(self, normalized_text: str):
        return core_extract_vs_team_pair(
            normalized_text,
            normalize_text=self._normalize_text,
            ipl_team_aliases=self.IPL_TEAM_ALIASES,
        )

    def _sports_answer_mentions_teams(self, answer_text: str, team_codes: list) -> bool:
        return core_sports_answer_mentions_teams(
            answer_text,
            team_codes,
            normalize_text=self._normalize_text,
            ipl_team_aliases=self.IPL_TEAM_ALIASES,
        )

    def _is_news_request(self, text: str) -> bool:
        return core_is_news_request(text, self._normalize_text)

    def _should_use_llm_web_grounding(self, text: str) -> bool:
        if self.llm_provider not in {"auto", "gemini"}:
            return False

        if not (GEMINI_AVAILABLE and self.gemini_key):
            return False

        normalized = self._normalize_text(text)
        if not normalized:
            return False

        if self._extract_direct_search_query(text):
            return True
        if self._is_news_request(text):
            return True
        if self._is_live_sports_query(normalized):
            return True

        web_markers = [
            "search", "web", "look up", "find online", "latest", "today", "current",
            "recent", "live", "news", "update", "trending",
        ]
        return any(marker in normalized for marker in web_markers)

    def _trim_messages_for_llm(self, messages: list, web_grounded: bool = False) -> list:
        if not messages:
            return []

        limit = self.max_context_messages_web if web_grounded else self.max_context_messages
        system_msg = None
        non_system = []
        for m in messages:
            if m.get("role") == "system" and system_msg is None:
                system_msg = m
            elif m.get("role") in {"user", "assistant"}:
                non_system.append(m)

        trimmed = non_system[-limit:] if limit > 0 else non_system
        if system_msg:
            return [system_msg] + trimmed
        return trimmed

    def _is_profile_query(self, normalized_text: str) -> bool:
        return core_is_profile_query(normalized_text)

    def _needs_detailed_answer(self, normalized_text: str) -> bool:
        return core_needs_detailed_answer(normalized_text)

    def _response_token_budget(
        self,
        normalized_text: str,
        input_type: str,
        use_web_grounding: bool,
        is_profile_query: bool,
    ) -> int:
        return core_response_token_budget(
            normalized_text=normalized_text,
            input_type=input_type,
            use_web_grounding=use_web_grounding,
            is_profile_query_flag=is_profile_query,
            quick_max_output_tokens=self.quick_max_output_tokens,
            default_max_output_tokens=self.default_max_output_tokens,
        )

    def _set_native_stderr_suppressed(self, suppress: bool):
        with self._stderr_redirect_lock:
            if suppress:
                self._stderr_redirect_depth += 1
                if self._stderr_redirect_depth > 1:
                    return
                try:
                    self._stderr_saved_fd = os.dup(2)
                    self._stderr_devnull_fd = os.open(os.devnull, os.O_WRONLY)
                    os.dup2(self._stderr_devnull_fd, 2)
                except OSError:
                    self._stderr_saved_fd = None
                    self._stderr_devnull_fd = None
            else:
                if self._stderr_redirect_depth == 0:
                    return
                self._stderr_redirect_depth -= 1
                if self._stderr_redirect_depth > 0:
                    return
                if self._stderr_saved_fd is not None:
                    try:
                        os.dup2(self._stderr_saved_fd, 2)
                    except OSError:
                        pass
                    try:
                        os.close(self._stderr_saved_fd)
                    except OSError:
                        pass
                    self._stderr_saved_fd = None
                if self._stderr_devnull_fd is not None:
                    try:
                        os.close(self._stderr_devnull_fd)
                    except OSError:
                        pass
                    self._stderr_devnull_fd = None

    def clear_history(self):
        """Clear conversation history (keeps system prompt)."""
        self.conversation_history = [
            {"role": "system", "content": self.SYSTEM_PROMPT}
        ]

    def listen_for_wake_or_text(self) -> tuple:
        """Continuously listen for wake word or wait for text from the queue."""
        if not VOICE_AVAILABLE:
            sys.stdout.write("\033[92mYou:\033[0m ")
            sys.stdout.flush()
            return input_queue.get()  # Block until text is typed

        recognizer = sr.Recognizer()
        wake_queue = queue.Queue()

        def callback(rec, audio):
            try:
                text = rec.recognize_google(audio).lower()
                is_wake, reason, similarity, intent = self._activation_signal(text)

                if is_wake:
                    wake_queue.put(("voice", ""))
                else:
                    # Helpful debug indicator so user sees what it heard instead of silently failing
                    sys.stdout.write(
                        f"\033[90m(Heard: '{text}' | score={similarity:.2f} intent={intent or '-'} reason={reason})\033[0m"
                        + " " * 8
                        + "\r"
                    )
                    sys.stdout.flush()
            except sr.UnknownValueError:
                pass
            except sr.RequestError:
                pass

        source = sr.Microphone()
        self._set_native_stderr_suppressed(True)
        try:
            with source:
                recognizer.adjust_for_ambient_noise(source, duration=0.2)

            sys.stdout.write("\033[94mCalcie:\033[0m [Type mode] Waiting for text or 'Hey Calcie'...\r")
            sys.stdout.flush()

            # Start background listener thread
            stop_listening = recognizer.listen_in_background(source, callback, phrase_time_limit=3)
            try:
                while True:
                    # 1. Check if user typed anything
                    try:
                        msg_type, content = input_queue.get_nowait()
                        if msg_type == "text":
                            if not content.strip():
                                print(" " * 80, end="\r")
                                print("\033[92mManual wake triggered!\033[0m")
                                return ("voice", "")
                            print(" " * 80, end="\r")
                            return ("text", content)
                    except queue.Empty:
                        pass

                    # 2. Check if background thread heard the wake word
                    try:
                        msg_type, content = wake_queue.get_nowait()
                        if msg_type == "voice":
                            print(" " * 80, end="\r")
                            print("\033[92mWake word detected!\033[0m")
                            return ("voice", "")
                    except queue.Empty:
                        pass

                    # Prevent busy looping
                    time.sleep(0.05)
            finally:
                stop_listening(wait_for_stop=True)

        except OSError:
            print(" " * 50, end="\r")
            return ("error", "")
        except Exception:
            print(" " * 50, end="\r")
            return ("error", "")
        finally:
            self._set_native_stderr_suppressed(False)

    def listen_voice(self) -> str:
        """Capture voice input using speech recognition."""
        if not VOICE_AVAILABLE:
            return ""

        recognizer = sr.Recognizer()
        self._set_native_stderr_suppressed(True)
        try:
            with sr.Microphone() as source:
                print("\033[94mCalcie:\033[0m I'm all ears...", end="\r")
                recognizer.adjust_for_ambient_noise(source, duration=0.2)

                # Keep listening until speech detected or timeout
                audio = recognizer.listen(source, timeout=10, phrase_time_limit=8)

                print(" " * 50, end="\r")

                try:
                    text = recognizer.recognize_google(audio).strip()
                    if len(text) < 2:
                        print(" " * 50, end="\r")
                        return ""

                    print(" " * 50, end="\r")
                    print(f"\033[92mYou:\033[0m {text}")
                    return text
                except sr.UnknownValueError:
                    print(" " * 50, end="\r")
                    return ""
                except sr.RequestError:
                    print(" " * 50, end="\r")
                    return ""

        except sr.WaitTimeoutError:
            print(" " * 50, end="\r")
            return ""
        except OSError:
            print(" " * 50, end="\r")
            return ""
        except Exception:
            print(" " * 50, end="\r")
            return ""
        finally:
            self._set_native_stderr_suppressed(False)


def print_banner(calcie=None):
    """Display the startup banner."""
    print("\n" + "=" * 50)
    print("  CALCIE - Personal AI Assistant")
    print("=" * 50)
    if VOICE_AVAILABLE:
        print("Voice input: Enabled")
    else:
        print("Voice input: Unavailable (pip install speechrecognition)")
    if TTS_AVAILABLE:
        print("Voice output: ON")
    else:
        print("Voice output: Unavailable")
    print("Commands: 'clear' (reset), 'exit' (quit)")
    if calcie is not None and not calcie.use_external_web_tools:
        print("External web tool search: OFF (using LLM web grounding)")
    elif SEARCH_AVAILABLE:
        print("External web tool search: ON")
    else:
        print("External web tool search: Unavailable (pip install duckduckgo-search)")
    print("=" * 50 + "\n")


def main():
    """Main entry point for Calcie."""
    calcie = Calcie()

    # Print LLM mode status
    llm_names = {
        "claude": "Claude API (Anthropic)",
        "gemini": "Gemini API (Google)",
        "grok": "Grok API (xAI)",
        "openai": "OpenAI API",
        "ollama": "Ollama (Local)"
    }
    mode_label = calcie.llm_provider

    if calcie.active_llm == "ollama":
        print(
            f"\033[93m[LLM mode: {mode_label} | Active: {llm_names.get(calcie.active_llm, calcie.active_llm)}]\033[0m"
        )
        try:
            urllib.request.urlopen(f"{calcie.ollama_url}/api/tags", timeout=5)
        except Exception:
            print("Warning: Could not connect to Ollama at localhost:11434")
            print("Please ensure Ollama is running:")
            print("  ollama pull mistral")
            print("(Starting anyway...)\n")
    else:
        print(
            f"\033[92m[LLM mode: {mode_label} | Active: {llm_names.get(calcie.active_llm, calcie.active_llm)}]\033[0m"
        )

    print_banner(calcie)

    # Start non-blocking text input reader
    t = threading.Thread(target=stdin_reader, daemon=True)
    t.start()

    tts_enabled = True  # Toggle for voice output
    state = "ACTIVE_LISTEN"  # start directly listening!

    while True:
        try:
            user_input = ""

            if state == "ACTIVE_LISTEN" and VOICE_AVAILABLE:
                user_input = calcie.listen_voice()
                
                # If they didn't say anything, it times out and drops to type mode
                if not user_input.strip():
                    state = "TYPE_MODE"
                    continue
            
            elif state == "TYPE_MODE" or not VOICE_AVAILABLE:
                result_type, content = calcie.listen_for_wake_or_text()
                
                if result_type == "text":
                    user_input = content
                    state = "ACTIVE_LISTEN" # Switch back to voice after handling
                elif result_type == "voice":
                    user_input = calcie.listen_voice()
                    if not user_input or not user_input.strip():
                        state = "TYPE_MODE"
                        continue
                    state = "ACTIVE_LISTEN" # Switched back to active voice
                else: 
                     # Error or unsupported
                     user_input = ""

            if not user_input or not user_input.strip():
                continue

            if user_input.lower() == "exit":
                calcie.speak("Goodbye!")
                print("\n\033[94mCalcie:\033[0m Goodbye!")
                break

            if user_input.lower() == "clear":
                calcie.clear_history()
                calcie.speak("Memory cleared")
                print("\033[94mCalcie:\033[0m Memory cleared.")
                continue

            print(" " * 50, end="\r", flush=True)
            response = calcie.chat(user_input)
            
            # Important: Block here until Calcie officially finishes speaking 
            # all output so her voice doesn't bleed back into the microphone stream!
            calcie.wait_for_speech()

        except KeyboardInterrupt:
            print("\n\n\033[94mCalcie:\033[0m Interrupted. Goodbye!")
            break
        except EOFError:
            print("\n\033[94mCalcie:\033[0m Input closed. Exiting.")
            break


if __name__ == "__main__":
    main()
