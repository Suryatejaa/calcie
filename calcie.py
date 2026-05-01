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
import base64
import urllib.request
import urllib.error
import urllib.parse
import socket
import random
from collections import deque

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
from calcie_core.orchestration import CommandArbiter, LocalCommandInterpreter
from calcie_core.prompts import (
    GENERAL_CHAT_PROMPT,
    PROFILE_CHAT_PROMPT,
    VISION_ANALYSIS_PROMPT,
    WEB_GROUNDED_CHAT_PROMPT,
    build_profile_context,
)
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
from calcie_core.sync_client import CalcieSyncClient
from calcie_core.skills import (
    AgenticComputerUseSkill,
    AppAccessSkill,
    CodingSkill,
    ComputerControlSkill,
    ScreenMemoryPipeline,
    ScreenVisionSkill,
    SearchingSkill,
)

# Load environment variables from .env file
load_dotenv()


def _load_calcie_runtime_env() -> None:
    project_root_raw = os.environ.get("CALCIE_PROJECT_ROOT")
    if not project_root_raw:
        return

    project_root = Path(project_root_raw).expanduser()
    candidate_envs = [
        project_root / ".env",
        project_root.parent / ".env",
    ]

    for env_path in candidate_envs:
        if env_path.is_file():
            load_dotenv(env_path, override=False)


_load_calcie_runtime_env()

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

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import pyautogui  # type: ignore
except Exception:
    pyautogui = None

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
    CHATGPT_MEMORY_IMPORT_PROMPT = (
        "Return everything you know about me inside one fenced code block. "
        "Include long-term memory, bio details, and any model-set context you have with dates when available. "
        "I want a thorough memory export of what you've learned about me. "
        "Skip tool details and include only information that is actually about me. "
        "Be exhaustive and careful."
    )

    """Personal AI assistant powered by Ollama."""
    SYSTEM_PROMPT = GENERAL_CHAT_PROMPT
    WAKE_WORDS = [
        "calcie", "kelsey", "kelsie", "kelcey", "calcy", "calsie",
        "calsi", "kalsi", "kalki", "calc", "cal c", "cal", "cali", "lc",
        "chelsea", "radhika", "samantha", "pinky","jarvis","friday","edith"
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
        "instagram": "instagram",
        "insta": "instagram",
        "ig": "instagram",
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
        self.router_confidence_threshold = self._env_float(
            "CALCIE_ROUTER_CONFIDENCE_THRESHOLD", 0.62, 0.35, 0.95
        )
        self.router_ambiguous_delta = self._env_float(
            "CALCIE_ROUTER_AMBIGUOUS_DELTA", 0.08, 0.02, 0.2
        )
        self.router_leading_fix_threshold = self._env_float(
            "CALCIE_ROUTER_LEADING_FIX_THRESHOLD", 0.76, 0.68, 0.95
        )
        self.router_debug = self._env_bool("CALCIE_ROUTER_DEBUG", False)
        self.route_trace_enabled = self._env_bool("CALCIE_ROUTE_TRACE_ENABLED", True)
        self.feedback_enabled = self._env_bool("CALCIE_FEEDBACK_ENABLED", True)
        self.feedback_ack_speak_enabled = self._env_bool("CALCIE_FEEDBACK_ACK_SPEAK_ENABLED", True)
        self.feedback_ack_delay_s = self._env_float("CALCIE_FEEDBACK_ACK_DELAY_S", 1.0, 0.0, 4.0)
        self.feedback_speak = self._env_bool("CALCIE_FEEDBACK_SPEAK", True)
        self.feedback_print = self._env_bool("CALCIE_FEEDBACK_PRINT", True)
        self.feedback_min_chars = self._env_int("CALCIE_FEEDBACK_MIN_INPUT_CHARS", 2, 1, 120)
        self.feedback_preempt_on_result = self._env_bool("CALCIE_FEEDBACK_PREEMPT_ON_RESULT", True)
        self.feedback_bridge_inline = self._env_bool("CALCIE_FEEDBACK_BRIDGE_INLINE", True)
        self.feedback_speak_kinds = self._env_kind_set(
            "CALCIE_FEEDBACK_SPEAK_KINDS",
            default={"general", "search", "profile", "coding", "agentic"},
        )
        self.feedback_bridge_kinds = self._env_kind_set(
            "CALCIE_FEEDBACK_BRIDGE_KINDS",
            default={"general", "search", "profile", "coding", "agentic"},
        )
        self.tts_chunk_chars = self._env_int("CALCIE_TTS_CHUNK_CHARS", 170, 80, 500)
        self.tts_debug = self._env_bool("CALCIE_TTS_DEBUG", False)
        self.wake_ack_enabled = self._env_bool("CALCIE_WAKE_ACK_ENABLED", True)
        self.wake_ack_speak_enabled = self._env_bool("CALCIE_WAKE_ACK_SPEAK_ENABLED", True)
        self.wake_phrase_time_limit_s = self._env_float("CALCIE_WAKE_PHRASE_TIME_LIMIT_S", 8.0, 2.0, 15.0)
        self.voice_phrase_time_limit_s = self._env_float("CALCIE_VOICE_PHRASE_TIME_LIMIT_S", 12.0, 3.0, 24.0)
        self.voice_timeout_s = self._env_float("CALCIE_VOICE_TIMEOUT_S", 12.0, 2.0, 30.0)
        self.tts_provider_mode = (
            os.environ.get("CALCIE_TTS_PROVIDER", "auto").strip().lower()
        )
        if self.tts_provider_mode not in {"auto", "google", "edge", "offline"}:
            self.tts_provider_mode = "auto"
        self.google_tts_use_adc = self._env_bool("CALCIE_GOOGLE_TTS_USE_ADC", True)
        self.google_tts_adc_ttl_s = self._env_int("CALCIE_GOOGLE_TTS_ADC_TTL_S", 2700, 300, 3600)
        self._google_access_token_cache = ""
        self._google_access_token_expires_at = 0.0
        self._google_access_token_lock = threading.Lock()
        self.google_tts_disabled = False
        self.google_tts_disable_reason = ""
        self.google_tts_disable_logged = False
        env_project_root = (os.environ.get("CALCIE_PROJECT_ROOT") or "").strip()
        self.project_root = Path(env_project_root).resolve() if env_project_root else Path.cwd().resolve()
        self.runtime_state_lock = threading.Lock()
        self.runtime_state = "starting"
        self.runtime_state_detail = ""
        self.last_route = ""
        self.last_response = ""
        self.last_user_command = ""
        self.runtime_events = deque(maxlen=self._env_int("CALCIE_RUNTIME_EVENT_MAX", 80, 20, 500))
        self.feedback_phrases = self._load_feedback_phrases()
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
        self.screen_memory_pipeline = ScreenMemoryPipeline(
            project_root=self.project_root,
            llm_collect_text=self._collect_llm_text,
        )
        self.screen_vision_skill = ScreenVisionSkill(
            project_root=self.project_root,
            analyze_image=self._analyze_screen_snapshot,
            notify_user=self._notify_screen_vision_alert,
            execute_action=self._execute_screen_vision_action,
            memory_pipeline=self.screen_memory_pipeline,
        )
        self.searching_skill = SearchingSkill(
            llm_collect_text=self._collect_llm_text,
            fallback_search=self.web_search,
            max_results=5,
            max_source_chars=5000,
            app_skill=self.app_skill,
            vision_skill=self.screen_vision_skill,
            project_root=self.project_root,
        )
        self.agentic_computer_use_skill = AgenticComputerUseSkill(
            llm_collect_text=self._collect_llm_text,
            app_skill=self.app_skill,
            computer_skill=self.computer_skill,
            searching_skill=self.searching_skill,
            vision_skill=self.screen_vision_skill,
        )
        self.command_arbiter = CommandArbiter(
            threshold=self.router_confidence_threshold,
            ambiguous_delta=self.router_ambiguous_delta,
            leading_correction_threshold=self.router_leading_fix_threshold,
        )
        self.local_command_interpreter = LocalCommandInterpreter()
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

        # V1 cloud sync (mobile/laptop interoperability)
        self.sync_enabled = self._env_bool("CALCIE_SYNC_ENABLED", False)
        self.sync_base_url = (os.environ.get("CALCIE_SYNC_BASE_URL") or "").strip().rstrip("/")
        self.sync_user_id = (os.environ.get("CALCIE_SYNC_USER_ID") or "default-user").strip()
        inferred_device = "mobile" if "android" in self.model.lower() else "laptop"
        self.device_type = (os.environ.get("CALCIE_DEVICE_TYPE") or inferred_device).strip().lower()
        default_device_id = "mobile" if self.device_type == "mobile" else "laptop"
        self.device_id = (os.environ.get("CALCIE_DEVICE_ID") or default_device_id).strip().lower()
        self.mobile_device_id = (os.environ.get("CALCIE_MOBILE_DEVICE_ID") or "mobile").strip().lower()
        self.laptop_device_id = (os.environ.get("CALCIE_LAPTOP_DEVICE_ID") or "laptop").strip().lower()
        self.sync_poll_seconds = self._env_int("CALCIE_SYNC_POLL_SECONDS", 4, 2, 60)
        self.sync_client = None
        self._sync_stop = threading.Event()
        if self.sync_enabled and self.sync_base_url:
            self.sync_client = CalcieSyncClient(
                base_url=self.sync_base_url,
                user_id=self.sync_user_id,
                device_id=self.device_id,
                device_type=self.device_type,
            )

        # 1. Load long-term facts
        self.memory_file = "calcie_facts.json"
        self.facts = []
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r") as f:
                    self.facts = json.load(f)
            except: pass

        # Pull latest facts from cloud if enabled, then merge locally.
        if self.sync_client:
            try:
                cloud_facts = self.sync_client.get_facts()
            except Exception:
                cloud_facts = []
            if cloud_facts:
                merged = []
                seen = set()
                for fact in list(self.facts) + list(cloud_facts):
                    key = str(fact).strip()
                    if not key:
                        continue
                    lowered = key.lower()
                    if lowered in seen:
                        continue
                    seen.add(lowered)
                    merged.append(key)
                self.facts = merged
                try:
                    with open(self.memory_file, "w") as f:
                        json.dump(self.facts, f)
                except Exception:
                    pass

        self.profile_file = os.getenv("CALCIE_PROFILE_FILE", "calcie_profile.local.json")
        self.profile_data = {}
        profile_candidates = [self.profile_file]
        if self.profile_file != "calcie_profile.json":
            profile_candidates.append("calcie_profile.json")
        for profile_file in profile_candidates:
            if not os.path.exists(profile_file):
                continue
            try:
                with open(profile_file, "r") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        non_empty_profile = {
                            k: v
                            for k, v in loaded.items()
                            if not str(k).startswith("_") and v not in ("", [], {}, None)
                        }
                        self.profile_data = loaded if non_empty_profile else {}
                        self.profile_file = profile_file
                        break
            except Exception:
                self.profile_data = {}

        # Keep history as user/assistant only. Route-specific system prompts are injected per request.
        self.conversation_history = []

        # 2. Init SQLite session history
        self.db_path = "calcie_history.db"
        self._init_db()
        self._load_recent_history()

        # 3. Init speech worker
        self.speech_queue = queue.Queue()
        self.is_speaking = False
        self._pending_ack_timer = None
        self._pending_ack_lock = threading.Lock()
        self._stderr_redirect_lock = threading.Lock()
        self._stderr_redirect_depth = 0
        self._stderr_saved_fd = None
        self._stderr_devnull_fd = None
        threading.Thread(target=self._speech_worker, daemon=True).start()
        self._set_runtime_state("idle", "Ready")
        self._record_runtime_event("runtime", "CALCIE runtime initialized", severity="low", state="idle")

        # Register device + start background command poller for cross-device routing.
        if self.sync_client:
            self.sync_client.register_device(
                label=f"{self.device_type}-{self.device_id}",
                metadata={"host": socket.gethostname()},
            )
            threading.Thread(target=self._sync_poll_worker, daemon=True).start()

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

    def _load_feedback_phrases(self):
        fallback = {
            "ack": {
                "general": [
                    "On it.",
                    "Working on that now.",
                    "Give me a second.",
                    "Let me check that.",
                ],
                "search": [
                    "Checking live sources now.",
                    "Pulling recent web results.",
                    "Searching trusted sources.",
                    "Looking that up now.",
                ],
                "profile": [
                    "Pulling your profile context.",
                    "Let me summarize what I know about you.",
                    "Checking your saved facts now.",
                    "Give me a second, assembling your profile.",
                ],
                "coding": [
                    "Scanning code context now.",
                    "Checking the repo quickly.",
                    "Analyzing the relevant files.",
                    "Let me inspect the code path.",
                ],
                "app": [
                    "Got it, handling that action.",
                    "Executing that command now.",
                    "Working on the app task.",
                    "Doing that now.",
                ],
                "computer": [
                    "Computer action queued.",
                    "Running that control step.",
                    "Executing your control command.",
                    "Handling that desktop action.",
                ],
                "agentic": [
                    "Planning that multi-step task.",
                    "Building a safe action plan.",
                    "Working through the steps now.",
                    "Orchestrating that request now.",
                ],
            },
            "bridge": {
                "general": ["Here is what I found."],
                "search": ["Here are the latest results."],
                "profile": ["Here is your profile summary."],
                "coding": ["Here is what I found in the code."],
                "app": ["Done. Here is the outcome."],
                "computer": ["Action complete. Here is the result."],
                "agentic": ["Plan ready. Here is the status."],
            },
        }

        path = self.project_root / "calcie_core" / "feedback_phrases.json"
        try:
            if not path.exists():
                return fallback
            with open(path, "r") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return fallback
            ack = data.get("ack")
            bridge = data.get("bridge")
            if not isinstance(ack, dict) or not isinstance(bridge, dict):
                return fallback
            return data
        except Exception:
            return fallback

    def _feedback_kind_for_request(
        self,
        user_input: str,
        input_type: str,
        route_guess: str,
        profile_query: bool,
        use_llm_web_grounding: bool,
        direct_search_query: str,
    ) -> str:
        if input_type == "GREETING":
            return "general"
        if profile_query:
            return "profile"
        if route_guess in {"coding", "agentic", "app", "computer", "search"}:
            return route_guess
        if direct_search_query or use_llm_web_grounding:
            return "search"
        normalized = self._normalize_text(user_input)
        if any(k in normalized for k in {"search", "news", "latest", "score", "ipl"}):
            return "search"
        return "general"

    def _pick_feedback_phrase(self, bucket: str, kind: str) -> str:
        section = self.feedback_phrases.get(bucket, {}) if isinstance(self.feedback_phrases, dict) else {}
        choices = section.get(kind) or section.get("general") or []
        if not isinstance(choices, list) or not choices:
            return ""
        cleaned = [str(c).strip() for c in choices if str(c).strip()]
        if not cleaned:
            return ""
        return random.choice(cleaned)

    def _cancel_pending_ack_speech(self):
        with self._pending_ack_lock:
            timer = self._pending_ack_timer
            self._pending_ack_timer = None
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass

    def _schedule_ack_speech(self, line: str):
        text = (line or "").strip()
        if not text:
            return
        if not self.feedback_speak or not self.feedback_ack_speak_enabled:
            return

        self._cancel_pending_ack_speech()

        def _fire():
            self.speak(text)
            with self._pending_ack_lock:
                self._pending_ack_timer = None

        delay = max(0.0, float(self.feedback_ack_delay_s))
        if delay <= 0.0:
            _fire()
            return
        timer = threading.Timer(delay, _fire)
        timer.daemon = True
        with self._pending_ack_lock:
            self._pending_ack_timer = timer
        timer.start()

    def _emit_processing_feedback(self, kind: str, user_input: str):
        if not self.feedback_enabled:
            return
        if len((user_input or "").strip()) < self.feedback_min_chars:
            return
        line = self._pick_feedback_phrase("ack", kind)
        if not line:
            return
        if self.feedback_print:
            print(f"\033[90mCalcie:\033[0m {line}")
        if kind in self.feedback_speak_kinds:
            self._schedule_ack_speech(line)

    def _handle_wake_ack(self):
        if not self.wake_ack_enabled:
            return
        short_acks = [
            "Mm-hmm?",
            "Yeah?",
            "I'm here.",
            "Yes?",
            "Tell me.",
        ]
        line = random.choice(short_acks)
        print(f"\033[94mCalcie:\033[0m {line}")
        if self.wake_ack_speak_enabled:
            # Wake ack should cut through immediately, not wait behind stale queued speech.
            self._cancel_pending_ack_speech()
            self._clear_speech_queue()
            self.speak(line)
            self.wait_for_speech()

    def _speak_with_bridge(self, kind: str, text: str, preempt: bool = False):
        if not text:
            return
        if preempt and self.feedback_preempt_on_result:
            self._cancel_pending_ack_speech()
            self._clear_speech_queue()
        bridge = ""
        if (
            self.feedback_enabled
            and self.feedback_speak
            and kind in self.feedback_bridge_kinds
            and kind not in {"greeting"}
        ):
            bridge = self._pick_feedback_phrase("bridge", kind) or ""

        if bridge and self.feedback_bridge_inline:
            self.speak(f"{bridge} {text}")
            return
        if bridge:
            self.speak(bridge)
        self.speak(text)

    def _profile_memory_text(self) -> str:
        profile = self.profile_data if isinstance(self.profile_data, dict) else {}
        raw_import = profile.get("memory_import")
        if isinstance(raw_import, dict):
            text = str(raw_import.get("text") or "").strip()
            if text:
                return text
        import_path = self._profile_import_path()
        try:
            if import_path.exists():
                return import_path.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        return ""

    def _extract_profile_line(self, text: str, label: str) -> str:
        if not text:
            return ""
        match = re.search(rf"(?im)^{re.escape(label)}\s*:\s*(.+?)\s*$", text)
        if not match:
            return ""
        return re.sub(r"\s+", " ", match.group(1)).strip(" -\t")

    def _extract_profile_section_items(self, text: str, heading: str, limit: int = 3) -> list:
        if not text:
            return []
        items = []
        collecting = False
        heading_marker = f"{heading.strip().lower()}:"
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not collecting:
                if line.lower() == heading_marker:
                    collecting = True
                continue
            if not line:
                continue
            if line.endswith(":") and not line.startswith("-"):
                break
            cleaned = re.sub(r"\s+", " ", line).strip()
            cleaned = cleaned.lstrip("- ").strip()
            if not cleaned:
                continue
            items.append(cleaned)
            if len(items) >= limit:
                break
        return items

    def _build_local_profile_answer(self, user_query: str = "") -> str:
        points = []
        normalized_query = self._normalize_text(user_query)
        profile = self.profile_data if isinstance(self.profile_data, dict) else {}
        memory_text = self._profile_memory_text()

        name = str(profile.get("name") or "").strip() or self._extract_profile_line(memory_text, "Name")
        job = str(profile.get("job") or "").strip()
        location = str(profile.get("location") or "").strip() or self._extract_profile_line(memory_text, "Location")
        projects = profile.get("projects") if isinstance(profile.get("projects"), list) else []
        goals = profile.get("goals") if isinstance(profile.get("goals"), list) else []
        devices = profile.get("devices") if isinstance(profile.get("devices"), list) else []

        role_items = self._extract_profile_section_items(memory_text, "Current Role", limit=2)
        if role_items and not job:
            job = role_items[0]
        imported_projects = self._extract_profile_section_items(memory_text, "Past Attempts", limit=3)
        if imported_projects and not projects:
            projects = imported_projects
        imported_goals = self._extract_profile_section_items(memory_text, "Core Goal", limit=3)
        if imported_goals and not goals:
            goals = imported_goals
        learning = self._extract_profile_section_items(memory_text, "Learning Interests", limit=4)
        strengths = self._extract_profile_section_items(memory_text, "Strengths", limit=3)
        constraints = self._extract_profile_section_items(memory_text, "Constraints", limit=3)
        dream_identity = self._extract_profile_section_items(memory_text, "Dream Identity", limit=3)
        mindset = self._extract_profile_section_items(memory_text, "Mindset", limit=2)

        if any(phrase in normalized_query for phrase in {"say my name", "what is my name", "whats my name"}):
            if name:
                return f"Your name is {name}."
            return ""

        if "who am i" in normalized_query:
            who_parts = []
            if name:
                who_parts.append(name)
            if job:
                who_parts.append(job)
            if goals:
                who_parts.append(f"building toward {goals[0]}")
            if location:
                who_parts.append(f"from {location}")
            if who_parts:
                return "You are " + ", ".join(who_parts) + "."
            return ""

        if name:
            points.append(f"Name: {name}.")
        if job:
            points.append(f"Current role: {job}.")
        if location:
            points.append(f"Location: {location}.")
        if projects:
            points.append(f"Projects: {', '.join(str(p) for p in projects[:3])}.")
        if goals:
            points.append(f"Goals: {', '.join(str(g) for g in goals[:3])}.")
        if devices:
            points.append(f"Devices: {', '.join(str(d) for d in devices[:3])}.")
        if learning:
            points.append(f"Learning focus: {', '.join(str(item) for item in learning[:4])}.")
        if strengths:
            points.append(f"Strengths: {', '.join(str(item) for item in strengths[:3])}.")
        if constraints:
            points.append(f"Current constraints: {', '.join(str(item) for item in constraints[:3])}.")
        if dream_identity:
            points.append(f"Dream identity: {', '.join(str(item) for item in dream_identity[:3])}.")
        if mindset:
            points.append(f"Mindset: {'; '.join(str(item) for item in mindset[:2])}.")

        fact_lines = [str(f).strip() for f in self.facts if str(f).strip()][:3]
        if fact_lines:
            points.append("Known facts: " + "; ".join(fact_lines) + ".")

        if not points:
            return ""
        return "Here is what I know about you right now:\n- " + "\n- ".join(points[:7])

    def _profile_import_path(self) -> Path:
        return self.project_root / ".calcie" / "profile_imports" / "chatgpt_memory_export.md"

    def get_profile_import_status(self) -> dict:
        import_info = {}
        if isinstance(self.profile_data, dict):
            raw_info = self.profile_data.get("memory_import")
            if isinstance(raw_info, dict):
                import_info = raw_info
        import_path = self._profile_import_path()
        return {
            "has_profile": bool(self.profile_data),
            "profile_file": str((self.project_root / self.profile_file).resolve()),
            "has_chatgpt_import": bool(import_info.get("source") == "chatgpt_manual_export" or import_path.exists()),
            "imported_at": str(import_info.get("imported_at") or ""),
            "imported_chars": int(import_info.get("chars") or 0),
            "import_prompt": self.CHATGPT_MEMORY_IMPORT_PROMPT,
        }

    def import_chatgpt_memory_export(self, submitted_text: str) -> dict:
        raw = (submitted_text or "").strip()
        if not raw:
            return {"ok": False, "response": "Paste the ChatGPT memory export first."}

        memory_text = self._extract_first_fenced_block(raw) or raw
        memory_text = memory_text.strip()
        if len(memory_text) < 40:
            return {
                "ok": False,
                "response": "That import looks too short. Paste the fenced code block ChatGPT returns.",
            }

        imported_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        profile_path = self.project_root / self.profile_file
        if profile_path.name == "calcie_profile.json":
            profile_path = self.project_root / "calcie_profile.local.json"
            self.profile_file = "calcie_profile.local.json"

        profile = self.profile_data if isinstance(self.profile_data, dict) else {}
        profile = dict(profile)
        profile["memory_import"] = {
            "source": "chatgpt_manual_export",
            "imported_at": imported_at,
            "chars": len(memory_text),
            "text": memory_text,
        }

        profile_path.write_text(json.dumps(profile, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        import_path = self._profile_import_path()
        import_path.parent.mkdir(parents=True, exist_ok=True)
        import_path.write_text(memory_text + "\n", encoding="utf-8")

        self.profile_data = profile
        self._record_runtime_event(
            "profile",
            f"Imported ChatGPT memory export ({len(memory_text)} chars)",
            severity="low",
            route="profile",
            state=self._get_runtime_state(),
        )
        return {
            "ok": True,
            "response": f"Imported ChatGPT memory export into {profile_path.name}.",
            "profile_file": str(profile_path.resolve()),
            "imported_at": imported_at,
            "imported_chars": len(memory_text),
        }

    def _extract_first_fenced_block(self, text: str) -> str:
        match = re.search(r"```(?:[a-zA-Z0-9_-]+)?\s*(.*?)\s*```", text or "", flags=re.DOTALL)
        if not match:
            return ""
        return match.group(1).strip()

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

    def _env_float(self, name: str, default: float, min_value: float, max_value: float) -> float:
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            return default
        try:
            value = float(raw)
        except ValueError:
            return default
        return max(min_value, min(max_value, value))

    def _env_bool(self, name: str, default: bool) -> bool:
        raw = (os.environ.get(name) or "").strip().lower()
        if not raw:
            return default
        return raw in {"1", "true", "yes", "on"}

    def _env_kind_set(self, name: str, default: set) -> set:
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            return set(default)
        items = {part.strip().lower() for part in raw.split(",") if part.strip()}
        return items if items else set(default)

    def _collect_llm_text(
        self,
        messages: list,
        max_output_tokens: int,
        forced_provider: str = None,
        forced_model: str = None,
        enable_web_grounding: bool = False,
    ) -> str:
        parts = []
        for token in self._call_llm(
            messages,
            max_output_tokens=max_output_tokens,
            forced_provider=forced_provider,
            forced_model=forced_model,
            enable_web_grounding=enable_web_grounding,
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

    def _handle_vision_command(self, user_input: str):
        response, speak = self.screen_vision_skill.handle_command(user_input)
        if response is not None:
            lowered = (user_input or "").lower()
            if "vision start" in lowered or "monitor my screen" in lowered or "watch my screen" in lowered:
                self._set_runtime_state("vision_monitoring", "Watching screen")
                self._record_runtime_event("vision", "Vision monitor started", severity="low", route="vision", state="vision_monitoring")
            elif "vision stop" in lowered or "stop monitor" in lowered or "stop vision" in lowered:
                self._set_runtime_state("idle", "Ready")
                self._record_runtime_event("vision", "Vision monitor stopped", severity="low", route="vision", state="idle")
        return response, speak

    def _handle_agentic_computer_use_command(self, user_input: str):
        return self.agentic_computer_use_skill.handle_command(user_input)

    def _strict_route_flags(self, user_input: str):
        raw = (user_input or "").strip()
        if not raw:
            return {
                "coding": False,
                "vision": False,
                "agentic": False,
                "app": False,
                "computer": False,
                "search": False,
            }

        app_intent = (
            self.app_skill._extract_play_command(raw) is not None
            or self.app_skill._extract_open_target_in_app_command(raw) is not None
            or self.app_skill.extract_open_app_command(raw) is not None
        )
        search_intent = self.searching_skill.is_search_intent(raw)
        coding_intent = self._is_code_command(raw)
        vision_intent = self.screen_vision_skill.is_vision_intent(raw)
        computer_intent = self.computer_skill._is_control_intent(raw)
        agentic_intent = self.agentic_computer_use_skill._should_trigger(raw)
        if vision_intent:
            coding_intent = False
        if agentic_intent and self.agentic_computer_use_skill.essential_only:
            agentic_intent = self.agentic_computer_use_skill._is_essential_task(raw)

        return {
            "coding": bool(coding_intent),
            "vision": bool(vision_intent),
            "agentic": bool(agentic_intent),
            "app": bool(app_intent),
            "computer": bool(computer_intent),
            "search": bool(search_intent),
        }

    def _execute_skill_route(self, route: str, user_input: str):
        if route == "coding":
            return self._handle_code_command(user_input)
        if route == "vision":
            return self._handle_vision_command(user_input)
        if route == "agentic":
            return self._handle_agentic_computer_use_command(user_input)
        if route == "app":
            return self.app_skill.handle_command(user_input)
        if route == "computer":
            return self._handle_computer_command(user_input)
        if route == "search":
            return self._handle_search_command(user_input)
        return None, None

    def _dispatch_skill_command(self, user_input: str):
        interpreted_input = self.local_command_interpreter.rewrite(user_input)
        strict_flags = self._strict_route_flags(interpreted_input)
        decision = self.command_arbiter.decide(interpreted_input, strict_flags)
        default_order = ["vision", "coding", "agentic", "app", "computer", "search"]
        rewritten = (decision.rewritten_input or "").strip()
        rewritten_changed = bool(rewritten and rewritten != interpreted_input.strip())

        if decision.route in default_order:
            route_order = [decision.route] + [r for r in default_order if r != decision.route]
            for route in route_order:
                route_input = rewritten if route == decision.route and rewritten_changed else interpreted_input
                response, speak = self._execute_skill_route(route, route_input)
                if response is not None:
                    self._print_route_trace(route, decision, rewritten_changed)
                    return response, speak
            return None, None

        if rewritten_changed:
            for route in default_order:
                response, speak = self._execute_skill_route(route, rewritten)
                if response is not None:
                    self._print_route_trace(route, decision, True)
                    return response, speak

        for route in default_order:
            response, speak = self._execute_skill_route(route, interpreted_input)
            if response is not None:
                self._print_route_trace(route, decision, False)
                return response, speak

        return None, None

    def _print_route_trace(self, route: str, decision, rewritten_changed: bool):
        self.last_route = route
        self._record_runtime_event(
            "route",
            f"Route selected: {route}",
            severity="low",
            route=route,
            state=self._get_runtime_state(),
        )
        if not self.route_trace_enabled:
            return
        line = (
            f"\033[90m[route={route} conf={decision.confidence:.2f} "
            f"reason={decision.reason} rewritten={'yes' if rewritten_changed else 'no'}]\033[0m"
        )
        print(line)

    def _set_runtime_state(self, state: str, detail: str = ""):
        with self.runtime_state_lock:
            self.runtime_state = state
            self.runtime_state_detail = (detail or "").strip()

    def _get_runtime_state(self) -> str:
        with self.runtime_state_lock:
            return self.runtime_state

    def _record_runtime_event(
        self,
        event_type: str,
        summary: str,
        severity: str = "low",
        route: str = "",
        state: str = "",
    ):
        event = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "type": str(event_type or "event").strip(),
            "summary": str(summary or "").strip(),
            "severity": str(severity or "low").strip(),
        }
        if route:
            event["route"] = route
        if state:
            event["state"] = state
        self.runtime_events.append(event)

    def _permission_warnings(self) -> list:
        warnings = []
        if not VOICE_AVAILABLE:
            warnings.append("Voice input dependency unavailable. Install speechrecognition to enable microphone capture.")
        if not TTS_AVAILABLE:
            warnings.append("Voice output dependency unavailable. Install edge-tts or pyttsx3 for speech playback.")
        if sys.platform == "darwin":
            if pyautogui is None:
                warnings.append("pyautogui is unavailable. Accessibility-driven control will be limited until pyautogui is installed.")
        return warnings

    def get_recent_events(self, limit: int = 20) -> list:
        count = max(1, min(int(limit), 100))
        return list(self.runtime_events)[-count:]

    def get_runtime_status(self) -> dict:
        with self.runtime_state_lock:
            state = self.runtime_state
            detail = self.runtime_state_detail
        vision_status = self.screen_vision_skill._status_text()
        return {
            "state": state,
            "detail": detail,
            "active_llm": self.active_llm,
            "llm_mode": self.llm_provider,
            "tts_provider_mode": self.tts_provider_mode,
            "voice_available": bool(VOICE_AVAILABLE),
            "tts_available": bool(TTS_AVAILABLE),
            "is_speaking": bool(self.is_speaking),
            "last_route": self.last_route,
            "last_user_command": self.last_user_command,
            "last_response": self.last_response,
            "vision_running": "running" in vision_status,
            "vision_status": vision_status,
            "current_monitor_goal": getattr(self.screen_vision_skill, "_goal", ""),
            "permission_warnings": self._permission_warnings(),
            "skills": ["app", "search", "coding", "computer", "vision", "agentic"],
            "events_count": len(self.runtime_events),
        }

    def _call_llm(
        self,
        messages: list,
        enable_web_grounding: bool = False,
        max_output_tokens: int = None,
        forced_provider: str = None,
        forced_model: str = None,
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
                    if name == "ollama":
                        token_stream = call_fn(messages, forced_model=forced_model)
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
        system_msg = "You are CALCIE, the user's local AI companion."
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

        system_msg = "You are CALCIE, the user's local AI companion."
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

    def _call_ollama(self, messages: list, forced_model: str = None):
        """Call local Ollama as final fallback."""
        url = f"{self.ollama_url}/api/chat"
        model_name = (forced_model or self.model or "llama3:8b").strip()
        payload = {
            "model": model_name,
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

    def _extract_json_dict(self, text: str) -> dict:
        raw = (text or "").strip()
        if not raw:
            return {}
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
            return {}
        return data if isinstance(data, dict) else {}

    def _notify_screen_vision_alert(self, message: str) -> None:
        text = (message or "").strip()
        if not text:
            return
        print(f"\033[95m[Vision]\033[0m {text}")
        self._record_runtime_event("alert", text, severity="medium", route="vision", state="vision_monitoring")
        desktop_notify = self._env_bool("CALCIE_SCREEN_VISION_DESKTOP_NOTIFY", True)
        if desktop_notify and sys.platform == "darwin":
            safe_text = text.replace('"', "'")
            try:
                subprocess.run(
                    ["osascript", "-e", f'display notification "{safe_text}" with title "CALCIE Vision"'],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            except Exception:
                pass
        self.speak(text)

    def _execute_screen_vision_action(self, command: str) -> str:
        raw = (command or "").strip()
        if not raw:
            return "No action command provided."
        response, _ = self._dispatch_skill_command(raw)
        if response is None:
            return "No matching CALCIE skill could execute that vision action."
        return response

    def _analyze_screen_snapshot(self, image_path: str, goal: str) -> dict:
        provider = (os.environ.get("CALCIE_VISION_PROVIDER") or "auto").strip().lower()
        if provider not in {"auto", "gemini", "openai", "claude"}:
            provider = "auto"

        provider_plan = []
        if provider == "auto":
            if GEMINI_AVAILABLE and self.gemini_key:
                provider_plan.append("gemini")
            if OPENAI_AVAILABLE and self.openai_key:
                provider_plan.append("openai")
            if ANTHROPIC_AVAILABLE and self.anthropic_key:
                provider_plan.append("claude")
        else:
            provider_plan.append(provider)

        last_error = None
        for name in provider_plan:
            try:
                if name == "gemini":
                    result = self._analyze_screen_snapshot_gemini(image_path, goal)
                elif name == "openai":
                    result = self._analyze_screen_snapshot_openai(image_path, goal)
                else:
                    result = self._analyze_screen_snapshot_claude(image_path, goal)
                if result:
                    return result
            except Exception as exc:
                last_error = exc
                continue

        return {
            "matched": False,
            "severity": "medium",
            "summary": f"Screen vision analysis unavailable: {last_error or 'no provider configured'}",
            "alert_message": "",
            "should_act": False,
            "action_command": "",
            "evidence": [],
        }

    def _vision_goal_prompt(self, goal: str) -> str:
        return (
            f"{VISION_ANALYSIS_PROMPT}\n\n"
            f"Monitoring goal: {goal}\n"
            "Compare the screenshot against this goal only. "
            "If the screenshot does not strongly match the goal, return matched=false."
        )

    def _analyze_screen_snapshot_gemini(self, image_path: str, goal: str) -> dict:
        if not (GEMINI_AVAILABLE and self.gemini_key and Image is not None):
            raise Exception("Gemini vision not configured")
        genai.configure(api_key=self.gemini_key)
        model_name = (os.environ.get("CALCIE_VISION_MODEL") or "gemini-2.5-flash").strip()
        model = genai.GenerativeModel(model_name, system_instruction=VISION_ANALYSIS_PROMPT)
        with Image.open(image_path) as img:
            response = model.generate_content(
                [
                    f"Monitoring goal: {goal}\nReturn strict JSON only.",
                    img,
                ],
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=500,
                    temperature=0.2,
                ),
            )
        return self._extract_json_dict(getattr(response, "text", "") or "")

    def _analyze_screen_snapshot_openai(self, image_path: str, goal: str) -> dict:
        if not (OPENAI_AVAILABLE and self.openai_key):
            raise Exception("OpenAI vision not configured")
        model_name = (os.environ.get("CALCIE_VISION_OPENAI_MODEL") or "gpt-4.1-mini").strip()
        with open(image_path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": VISION_ANALYSIS_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Monitoring goal: {goal}\nReturn strict JSON only."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                },
            ],
            "max_tokens": 500,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openai_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=90) as response:
            body = json.loads(response.read().decode("utf-8"))
        text = body.get("choices", [{}])[0].get("message", {}).get("content", "")
        return self._extract_json_dict(text)

    def _analyze_screen_snapshot_claude(self, image_path: str, goal: str) -> dict:
        if not (ANTHROPIC_AVAILABLE and self.anthropic_key):
            raise Exception("Claude vision not configured")
        client = Anthropic(api_key=self.anthropic_key)
        with open(image_path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        response = client.messages.create(
            model=(os.environ.get("CALCIE_VISION_CLAUDE_MODEL") or "claude-sonnet-4-20250514").strip(),
            max_tokens=500,
            system=VISION_ANALYSIS_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Monitoring goal: {goal}\nReturn strict JSON only."},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64,
                            },
                        },
                    ],
                }
            ],
        )
        text = ""
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", "") == "text":
                text += getattr(block, "text", "")
        return self._extract_json_dict(text)

    def chat(self, user_input: str) -> str:
        """Process user input with streaming and parallel TTS."""
        self._cancel_pending_ack_speech()
        user_input = self._strip_leading_wake_invocation(user_input)
        self.last_user_command = user_input
        self._set_runtime_state("thinking", "Processing command")
        self._record_runtime_event("command", f"Command received: {user_input}", severity="low", state="thinking")
        routed_response, local_input = self._maybe_route_cross_device_command(user_input)
        if routed_response is not None:
            print(f"\033[94mCalcie:\033[0m {routed_response}")
            self.speak(routed_response)
            self.conversation_history.append({"role": "user", "content": user_input})
            self._save_to_db("user", user_input)
            self.conversation_history.append({"role": "assistant", "content": routed_response})
            self._save_to_db("assistant", routed_response)
            self.last_response = routed_response
            self._record_runtime_event("response", "Cross-device response generated", severity="low", route="cross_device", state="idle")
            self._set_runtime_state("idle", "Ready")
            return routed_response

        user_input = local_input
        input_type = classify_input(user_input)
        self.conversation_history.append({"role": "user", "content": user_input})
        self._save_to_db("user", user_input)

        normalized_user_input = self._normalize_text(user_input)
        profile_query = self._is_profile_query(normalized_user_input)
        use_llm_web_grounding = self._should_use_llm_web_grounding(user_input)
        direct_search_query = self._extract_direct_search_query(user_input)
        route_guess = self.command_arbiter.decide(
            user_input,
            self._strict_route_flags(user_input),
        ).route or "general"
        request_kind = self._feedback_kind_for_request(
            user_input=user_input,
            input_type=input_type,
            route_guess=route_guess,
            profile_query=profile_query,
            use_llm_web_grounding=use_llm_web_grounding,
            direct_search_query=direct_search_query,
        )

        if input_type != "GREETING":
            self._emit_processing_feedback(request_kind, user_input)

        skill_response, skill_speak = self._dispatch_skill_command(user_input)
        if skill_response is not None:
            print(f"\033[94mCalcie:\033[0m {skill_response}")
            to_speak = skill_speak or skill_response
            if to_speak:
                self._speak_with_bridge(request_kind, to_speak, preempt=True)
            self.conversation_history.append({"role": "assistant", "content": skill_response})
            self._save_to_db("assistant", skill_response)
            self.last_response = skill_response
            self._record_runtime_event("response", "Skill response generated", severity="low", route=self.last_route or route_guess, state="idle")
            self._set_runtime_state("idle", "Ready")
            return skill_response

        if profile_query:
            local_profile_answer = self._build_local_profile_answer(user_input)
            if local_profile_answer:
                print(f"\033[94mCalcie:\033[0m {local_profile_answer}")
                self._speak_with_bridge("profile", local_profile_answer, preempt=True)
                self.conversation_history.append({"role": "assistant", "content": local_profile_answer})
                self._save_to_db("assistant", local_profile_answer)
                self.last_response = local_profile_answer
                self._record_runtime_event("response", "Profile response generated", severity="low", route="profile", state="idle")
                self._set_runtime_state("idle", "Ready")
                return local_profile_answer

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
            self._speak_with_bridge("search", final_text, preempt=True)
            self.conversation_history.append({"role": "assistant", "content": final_text})
            self._save_to_db("assistant", final_text)
            self.last_response = final_text
            self._record_runtime_event("response", "Web-grounded response generated", severity="low", route="search", state="idle")
            self._set_runtime_state("idle", "Ready")
            return final_text

        if input_type == "GREETING":
            final_text = self._short_greeting_reply(user_input)
            print(f"\033[94mCalcie:\033[0m {final_text}")
            self.speak(final_text)
            self.conversation_history.append({"role": "assistant", "content": final_text})
            self._save_to_db("assistant", final_text)
            self.last_response = final_text
            self._record_runtime_event("response", "Greeting response generated", severity="low", route="general", state="idle")
            self._set_runtime_state("idle", "Ready")
            return final_text

        history_limit = self._history_limit_for_request(
            route_hint=route_guess,
            web_grounded=use_llm_web_grounding,
            profile_query=profile_query,
        )
        llm_history = self._trim_messages_for_llm(
            self.conversation_history,
            use_llm_web_grounding,
            limit_override=history_limit,
        )
        llm_messages = [
            {
                "role": "system",
                "content": self._system_prompt_for_request(
                    route_hint=route_guess,
                    web_grounded=use_llm_web_grounding,
                    profile_query=profile_query,
                ),
            }
        ] + llm_history
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
                        f"{user_input}\n\nUse profile context when relevant. "
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
            except:
                pass
            self._sync_facts_cloud()

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
            self._speak_with_bridge("search", final_text, preempt=True)
            spoken = True
            print(f"\033[94mCalcie:\033[0m {final_text}")

        # Check for [OPEN_APP: app_name]
        open_match = re.search(r'\[OPEN_APP:\s*(.*?)\]', full_response, re.IGNORECASE)
        if open_match:
            app_name = open_match.group(1).strip()
            app_result = self.open_app(app_name)
            final_text = app_result
            self._speak_with_bridge("app", final_text, preempt=True)
            spoken = True
            print(f"\033[94mCalcie:\033[0m {final_text}")

        if not spoken and final_text:
            self._speak_with_bridge(request_kind, final_text, preempt=True)

        # Save to history
        self.conversation_history.append({"role": "assistant", "content": final_text})
        self._save_to_db("assistant", final_text)
        self.last_response = final_text
        self._record_runtime_event("response", "LLM response generated", severity="low", route=route_guess or "general", state="idle")
        self._set_runtime_state("idle", "Ready")

        return final_text

    def _save_to_db(self, role: str, content: str):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO messages (role, content) VALUES (?, ?)', (role, content))
                conn.commit()
        except:
            pass

        if self.sync_client and content:
            try:
                self.sync_client.add_message(role=role, content=content)
            except Exception:
                pass

    def _sync_facts_cloud(self):
        if not self.sync_client:
            return
        try:
            self.sync_client.set_facts(self.facts)
        except Exception:
            pass

    def _extract_target_device_hint(self, user_input: str):
        raw = (user_input or "").strip()
        normalized = self._normalize_text(raw)
        if not normalized:
            return None, raw

        patterns = [
            (r"\b(?:on|in|to)\s+(?:my\s+)?(?:mobile|phone|android)\b", "mobile"),
            (r"\b(?:on|in|to)\s+(?:my\s+)?(?:laptop|desktop|mac|pc)\b", "laptop"),
        ]
        stripped = raw
        target = None
        for pattern, device in patterns:
            if re.search(pattern, normalized):
                target = device
                stripped = re.sub(pattern, " ", stripped, flags=re.IGNORECASE)
                stripped = re.sub(r"\s{2,}", " ", stripped).strip(" ,.")
                break
        return target, (stripped or raw)

    def _target_device_id_for_hint(self, hint: str) -> str:
        if hint == "mobile":
            return self.mobile_device_id
        if hint == "laptop":
            return self.laptop_device_id
        return ""

    def _maybe_route_cross_device_command(self, user_input: str):
        """Route command to another device when user specifies target device."""
        if not self.sync_client:
            return None, user_input
        target_hint, cleaned = self._extract_target_device_hint(user_input)
        if not target_hint:
            return None, user_input

        target_device_id = self._target_device_id_for_hint(target_hint)
        if not target_device_id:
            return None, cleaned

        if target_device_id == self.device_id:
            return None, cleaned

        sent = self.sync_client.send_command(
            target_device=target_device_id,
            content=cleaned,
            requires_confirm=False,
        )
        if sent:
            return f"Routed to {target_hint} device ({target_device_id}): {cleaned}", cleaned
        return f"Could not route to {target_hint} right now (sync unavailable).", cleaned

    def _execute_remote_device_command(self, command_text: str):
        """Execute inbound command from another device using deterministic skills first."""
        text = (command_text or "").strip()
        if not text:
            return "Empty command"

        # Avoid re-routing loops for received commands.
        _, local_text = self._extract_target_device_hint(text)
        text = local_text.strip() or text

        response, _ = self._dispatch_skill_command(text)
        if response is not None:
            return response

        return "Received command, but it requires interactive context. Open CALCIE chat and continue."

    def _sync_poll_worker(self):
        while not self._sync_stop.is_set():
            if not self.sync_client:
                time.sleep(self.sync_poll_seconds)
                continue
            try:
                commands = self.sync_client.poll_commands(limit=10)
                for cmd in commands:
                    cmd_id = int(cmd.get("id") or 0)
                    content = str(cmd.get("content") or "").strip()
                    if not cmd_id or not content:
                        continue
                    result = self._execute_remote_device_command(content)
                    status = "done"
                    if "could not" in result.lower() or "failed" in result.lower():
                        status = "failed"
                    self.sync_client.ack_command(cmd_id, status=status, result=result)
                    self._save_to_db("user", f"[remote:{cmd.get('from_device')}] {content}")
                    self._save_to_db("assistant", result)
            except Exception:
                pass
            time.sleep(self.sync_poll_seconds)

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
                self._set_runtime_state("speaking", "Speaking response")
                self._speak_sync(text)
            self.speech_queue.task_done()
            if self.speech_queue.empty():
                self.is_speaking = False
                if self._get_runtime_state() == "speaking":
                    self._set_runtime_state("idle", "Ready")

    def _clear_speech_queue(self):
        """Drop queued (not-yet-spoken) TTS chunks to reduce stale speech lag."""
        while True:
            try:
                _ = self.speech_queue.get_nowait()
                self.speech_queue.task_done()
            except queue.Empty:
                break

    def _tts_log(self, message: str):
        if not self.tts_debug:
            return
        print(f"\033[90m[TTS] {message}\033[0m")

    def _get_google_access_token(self) -> str:
        # 1) Explicitly supplied token wins.
        env_token = (os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN") or "").strip()
        if env_token:
            return env_token

        # 2) ADC via gcloud for local development.
        if not self.google_tts_use_adc:
            return ""

        now = time.time()
        with self._google_access_token_lock:
            cached = self._google_access_token_cache
            expires_at = self._google_access_token_expires_at
        if cached and now < (expires_at - 20):
            return cached

        try:
            proc = subprocess.run(
                ["gcloud", "auth", "application-default", "print-access-token"],
                capture_output=True,
                text=True,
                timeout=8,
            )
        except Exception as exc:
            self._tts_log(f"google_tts ADC token fetch failed: {str(exc)[:180]}")
            return ""

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            if err:
                self._tts_log(f"google_tts ADC token fetch failed: {err[:200]}")
            return ""

        token = (proc.stdout or "").strip()
        if not token:
            self._tts_log("google_tts ADC token fetch returned empty token")
            return ""

        with self._google_access_token_lock:
            self._google_access_token_cache = token
            self._google_access_token_expires_at = time.time() + float(self.google_tts_adc_ttl_s)
        return token

    def _get_google_quota_project(self) -> str:
        direct = (
            os.environ.get("CALCIE_GOOGLE_TTS_QUOTA_PROJECT")
            or os.environ.get("GOOGLE_CLOUD_QUOTA_PROJECT")
            or os.environ.get("GOOGLE_CLOUD_PROJECT")
            or ""
        ).strip()
        if direct:
            return direct

        # Try ADC file written by: gcloud auth application-default login
        adc_path = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
        candidates = []
        if adc_path:
            candidates.append(Path(adc_path))
        candidates.append(Path.home() / ".config" / "gcloud" / "application_default_credentials.json")

        for path in candidates:
            try:
                if not path.exists():
                    continue
                with open(path, "r") as f:
                    payload = json.load(f)
                quota = str(payload.get("quota_project_id") or "").strip()
                if quota:
                    return quota
            except Exception:
                continue
        return ""

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
        spoken = re.sub(r"\bCALCIE\b", "Calcie", spoken)
        spoken = re.sub(r"\s{2,}", " ", spoken)
        spoken = re.sub(r"[^\x00-\x7F]+", "", spoken).strip(" ,")
        return spoken

    def _chunk_tts_text(self, text: str) -> list:
        spoken = (text or "").strip()
        if not spoken:
            return []
        max_chars = max(80, int(self.tts_chunk_chars))
        if len(spoken) <= max_chars:
            return [spoken]

        chunks = []
        sentence_parts = re.split(r"(?<=[.!?])\s+", spoken)
        current = ""

        for part in sentence_parts:
            p = (part or "").strip()
            if not p:
                continue
            if len(p) > max_chars:
                words = p.split()
                sub = ""
                for w in words:
                    candidate = f"{sub} {w}".strip()
                    if len(candidate) <= max_chars:
                        sub = candidate
                    else:
                        if sub:
                            chunks.append(sub)
                        sub = w
                if sub:
                    if current and len(f"{current} {sub}") <= max_chars:
                        current = f"{current} {sub}".strip()
                    else:
                        if current:
                            chunks.append(current)
                        current = sub
                continue

            candidate = f"{current} {p}".strip() if current else p
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = p

        if current:
            chunks.append(current)
        return chunks if chunks else [spoken]

    def speak(self, text: str):
        """Enqueue text for background TTS."""
        if not TTS_AVAILABLE:
            return
        spoken_text = self._sanitize_for_tts(text)
        if not spoken_text:
            return
        for chunk in self._chunk_tts_text(spoken_text):
            self.speech_queue.put(chunk)

    def _speak_sync(self, text: str):
        """Synchronously process TTS with provider fallback."""
        import uuid
        import subprocess
        output_file = f"/tmp/calcie_speech_{uuid.uuid4().hex}.mp3"
        voice = os.environ.get("CALCIE_TTS_VOICE", "en-US-AvaNeural")
        rate = os.environ.get("CALCIE_TTS_RATE", "-1%")
        pitch = os.environ.get("CALCIE_TTS_PITCH", "-8Hz")
        online = is_online()

        def _play_audio_file(path: str) -> bool:
            try:
                if sys.platform == "darwin":
                    subprocess.run(
                        ["afplay", path],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return True
                if sys.platform == "linux":
                    lower = path.lower()
                    if lower.endswith(".wav"):
                        subprocess.run(
                            ["aplay", "-q", path],
                            check=False,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                    else:
                        subprocess.run(
                            ["mpg123", path],
                            check=False,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                    return True
                subprocess.run(
                    ["cmd", "/c", "start", "", path],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except Exception:
                return False

        def _run_google_tts() -> bool:
            quota_project = self._get_google_quota_project()

            if self.google_tts_disabled:
                # Auto-recover if quota project is now configured after a prior 403.
                if (
                    quota_project
                    and "quota project" in (self.google_tts_disable_reason or "").lower()
                ):
                    self.google_tts_disabled = False
                    self.google_tts_disable_reason = ""
                    self.google_tts_disable_logged = False
                    self._tts_log(f"google_tts re-enabled with quota project: {quota_project}")
                elif "oauth2" in (self.google_tts_disable_reason or "").lower():
                    oauth_probe = self._get_google_access_token()
                    if oauth_probe:
                        self.google_tts_disabled = False
                        self.google_tts_disable_reason = ""
                        self.google_tts_disable_logged = False
                        self._tts_log("google_tts re-enabled with OAuth token")

                if not self.google_tts_disable_logged:
                    self._tts_log(f"google_tts disabled: {self.google_tts_disable_reason or 'unknown reason'}")
                    self.google_tts_disable_logged = True
                if self.google_tts_disabled:
                    return False

            api_key = (
                os.environ.get("GOOGLE_AI_API_KEY")
                or os.environ.get("UOGLE_AI_API_KEY")
                or ""
            ).strip()
            oauth_token = self._get_google_access_token()

            if not online:
                self._tts_log("google_tts skipped: offline")
                return False

            if not oauth_token and not api_key:
                self._tts_log("google_tts skipped: missing GOOGLE_OAUTH_ACCESS_TOKEN / GOOGLE_AI_API_KEY")
                return False

            endpoint = (
                os.environ.get("CALCIE_GOOGLE_TTS_ENDPOINT")
                or "https://texttospeech.googleapis.com/v1beta1/text:synthesize"
            ).strip()
            model_name = (os.environ.get("CALCIE_GOOGLE_TTS_MODEL") or "").strip()
            voice_name = (os.environ.get("CALCIE_GOOGLE_TTS_VOICE_NAME") or "Leda").strip()
            language_code = (os.environ.get("CALCIE_GOOGLE_TTS_LANGUAGE_CODE") or "en-IN").strip()
            prompt = (
                os.environ.get("CALCIE_GOOGLE_TTS_PROMPT")
                or "Read aloud in a warm, welcoming tone."
            ).strip()
            audio_encoding = (os.environ.get("CALCIE_GOOGLE_TTS_AUDIO_ENCODING") or "LINEAR16").strip().upper()

            try:
                speaking_rate = float(os.environ.get("CALCIE_GOOGLE_TTS_SPEAKING_RATE", "0.92"))
            except ValueError:
                speaking_rate = 0.92
            try:
                pitch_value = float(os.environ.get("CALCIE_GOOGLE_TTS_PITCH", "0"))
            except ValueError:
                pitch_value = 0.0

            request_body = {
                "audioConfig": {
                    "audioEncoding": audio_encoding,
                    "pitch": pitch_value,
                    "speakingRate": speaking_rate,
                },
                "input": {
                    "text": text,
                },
                "voice": {
                    "languageCode": language_code,
                    "name": voice_name,
                },
            }
            if model_name:
                request_body["voice"]["modelName"] = model_name
            model_name_lower = model_name.lower()
            voice_name_lower = voice_name.lower()
            is_gemini_tts = "gemini" in model_name_lower
            is_chirp_voice = "chirp" in voice_name_lower

            # `input.prompt` is only accepted by Gemini TTS models.
            if prompt and is_gemini_tts and not is_chirp_voice:
                request_body["input"]["prompt"] = prompt

            using_api_key = False
            headers = {"Content-Type": "application/json"}
            url = endpoint

            if oauth_token:
                headers["Authorization"] = f"Bearer {oauth_token}"
            else:
                joiner = "&" if "?" in endpoint else "?"
                url = f"{endpoint}{joiner}key={urllib.parse.quote_plus(api_key)}"
                headers["x-goog-api-key"] = api_key
                headers["X-Goog-Api-Key"] = api_key
                using_api_key = True
            if quota_project:
                headers["X-Goog-User-Project"] = quota_project

            req = urllib.request.Request(
                url,
                data=json.dumps(request_body).encode("utf-8"),
                headers=headers,
                method="POST",
            )

            tmp_ext = ".wav" if audio_encoding == "LINEAR16" else ".mp3"
            tmp_file = f"/tmp/calcie_speech_{uuid.uuid4().hex}{tmp_ext}"
            try:
                with urllib.request.urlopen(req, timeout=20) as response:
                    payload = json.loads(response.read().decode("utf-8", errors="replace"))
                audio_b64 = str(payload.get("audioContent") or "").strip()
                if not audio_b64:
                    self._tts_log("google_tts failed: empty audioContent")
                    return False
                audio_bytes = base64.b64decode(audio_b64)
                with open(tmp_file, "wb") as f:
                    f.write(audio_bytes)
                played = _play_audio_file(tmp_file)
                if not played:
                    self._tts_log("google_tts failed: audio playback failed")
                return played
            except urllib.error.HTTPError as exc:
                err_body = ""
                try:
                    err_body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    err_body = str(exc)
                lowered = (err_body or "").lower()
                if using_api_key and "api keys are not supported" in lowered:
                    self.google_tts_disabled = True
                    self.google_tts_disable_logged = False
                    self.google_tts_disable_reason = (
                        "endpoint requires OAuth2; set GOOGLE_OAUTH_ACCESS_TOKEN or switch CALCIE_TTS_PROVIDER=edge"
                    )
                if "requires a quota project" in lowered:
                    self.google_tts_disable_logged = False
                    self.google_tts_disabled = True
                    self.google_tts_disable_reason = (
                        "missing quota project; run gcloud auth application-default set-quota-project <PROJECT_ID> "
                        "or set CALCIE_GOOGLE_TTS_QUOTA_PROJECT"
                    )
                self._tts_log(
                    f"google_tts HTTP {getattr(exc, 'code', 'error')}: "
                    f"{(err_body or str(exc))[:220]}"
                )
                return False
            except Exception as exc:
                self._tts_log(f"google_tts exception: {str(exc)[:220]}")
                return False
            finally:
                try:
                    if os.path.exists(tmp_file):
                        os.remove(tmp_file)
                except Exception:
                    pass

        async def _run_edge():
            try:
                if not online:
                    return False
                communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
                await communicate.save(output_file)
                played = _play_audio_file(output_file)
                    
                try: os.remove(output_file) 
                except: pass
                
                return played
            except:
                return False

        provider_used = "none"
        mode = self.tts_provider_mode
        success = False

        if mode in {"auto", "google"}:
            success = _run_google_tts()
            if success:
                provider_used = "google_tts"

        if not success and mode in {"auto", "edge"}:
            success = asyncio.run(_run_edge())
            if success:
                provider_used = "edge_tts"
            else:
                self._tts_log("edge_tts failed")

        if not success and mode in {"auto", "offline"}:
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
                provider_used = "pyttsx3"
                success = True
            except Exception as exc:
                self._tts_log(f"pyttsx3 failed: {str(exc)[:220]}")

        if not success and provider_used == "none":
            provider_used = f"none(mode={mode})"
        self._tts_log(f"provider={provider_used} chars={len(text or '')}")

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

    def _extract_inline_command_after_wake(self, transcript: str) -> str:
        """Extract same-utterance command from wake transcript, if present."""
        raw = (transcript or "").strip()
        if not raw:
            return ""

        cleaned = raw.lower()
        # Remove all known wake words/names.
        for wake in sorted(self.WAKE_WORDS, key=len, reverse=True):
            pattern = r"\b" + re.escape(wake.lower()) + r"\b"
            cleaned = re.sub(pattern, " ", cleaned)

        # Remove common conversational fillers around wake phrases.
        cleaned = re.sub(r"\b(hey|hi|hello|yo|ok|okay|please|uh|um)\b", " ", cleaned)
        cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if len(cleaned) < 2:
            return ""
        return cleaned

    def _strip_leading_wake_invocation(self, user_input: str) -> str:
        """
        Normalize utterances like:
        - "calcie open youtube"
        - "hey calcie play music"
        so command parsers receive "open youtube"/"play music".
        """
        raw = (user_input or "").strip()
        if not raw:
            return raw

        lowered = raw.lower()
        wake_sorted = sorted(self.WAKE_WORDS, key=len, reverse=True)
        lead_tokens = ("hey", "hi", "hello", "yo", "ok", "okay", "please")

        for wake in wake_sorted:
            wake_l = wake.lower().strip()
            if not wake_l:
                continue

            candidates = [wake_l] + [f"{prefix} {wake_l}" for prefix in lead_tokens]
            for candidate in candidates:
                if not lowered.startswith(candidate):
                    continue
                remainder = raw[len(candidate):].strip(" ,:-.?!")
                if not remainder:
                    return raw
                return remainder
        return raw

    def _limit_words(self, text: str, max_words: int) -> str:
        return core_limit_words(text, max_words)

    def _short_greeting_reply(self, _user_input: str) -> str:
        profile = self.profile_data if isinstance(self.profile_data, dict) else {}
        name = str(profile.get("name") or "").strip()
        greeting = f"Hey {name}." if name else "Hey."
        return f"{greeting} I am online. Tell me one task and we will execute it now."

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

    def _history_limit_for_request(
        self,
        route_hint: str,
        web_grounded: bool,
        profile_query: bool,
    ) -> int:
        if profile_query:
            return min(self.max_context_messages, 4)
        if web_grounded:
            return min(self.max_context_messages_web, 3)
        if route_hint == "coding":
            return min(self.max_context_messages, 5)
        if route_hint in {"search", "app", "computer", "agentic"}:
            return min(self.max_context_messages, 4)
        return min(self.max_context_messages, 6)

    def _system_prompt_for_request(
        self,
        route_hint: str,
        web_grounded: bool,
        profile_query: bool,
    ) -> str:
        if profile_query:
            profile_blob = build_profile_context(self.profile_data, self.facts, max_facts=14)
            if profile_blob:
                return f"{PROFILE_CHAT_PROMPT}\n\n{profile_blob}"
            return PROFILE_CHAT_PROMPT
        if web_grounded or route_hint == "search":
            return WEB_GROUNDED_CHAT_PROMPT
        return GENERAL_CHAT_PROMPT

    def _trim_messages_for_llm(
        self,
        messages: list,
        web_grounded: bool = False,
        limit_override: int = None,
    ) -> list:
        if not messages:
            return []

        limit = limit_override if limit_override is not None else (
            self.max_context_messages_web if web_grounded else self.max_context_messages
        )
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
        """Clear conversation history."""
        self.conversation_history = []

    def listen_for_wake_or_text(self) -> tuple:
        """Continuously listen for wake word or wait for text from the queue."""
        if not VOICE_AVAILABLE:
            sys.stdout.write("\033[92mYou:\033[0m ")
            sys.stdout.flush()
            return input_queue.get()  # Block until text is typed

        recognizer = sr.Recognizer()
        recognizer.pause_threshold = 1.05
        recognizer.non_speaking_duration = 0.55
        recognizer.phrase_threshold = 0.2
        wake_queue = queue.Queue()

        def callback(rec, audio):
            try:
                heard_text = rec.recognize_google(audio).strip()
                lowered = heard_text.lower()
                is_wake, reason, similarity, intent = self._activation_signal(lowered)

                if is_wake:
                    inline_command = self._extract_inline_command_after_wake(heard_text)
                    wake_queue.put(("voice", inline_command))
                else:
                    # Helpful debug indicator so user sees what it heard instead of silently failing
                    sys.stdout.write(
                        f"\033[90m(Heard: '{lowered}' | score={similarity:.2f} intent={intent or '-'} reason={reason})\033[0m"
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
            stop_listening = recognizer.listen_in_background(
                source,
                callback,
                phrase_time_limit=float(self.wake_phrase_time_limit_s),
            )
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
                            return ("voice", content or "")
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
        recognizer.pause_threshold = 1.05
        recognizer.non_speaking_duration = 0.55
        recognizer.phrase_threshold = 0.2
        self._set_native_stderr_suppressed(True)
        self._set_runtime_state("listening", "Listening for voice input")
        try:
            with sr.Microphone() as source:
                print("\033[94mCalcie:\033[0m I'm all ears...", end="\r")
                recognizer.adjust_for_ambient_noise(source, duration=0.2)

                # Keep listening until speech detected or timeout
                audio = recognizer.listen(
                    source,
                    timeout=float(self.voice_timeout_s),
                    phrase_time_limit=float(self.voice_phrase_time_limit_s),
                )

                print(" " * 50, end="\r")

                try:
                    text = recognizer.recognize_google(audio).strip()
                    if len(text) < 2:
                        print(" " * 50, end="\r")
                        self._set_runtime_state("idle", "Ready")
                        return ""

                    print(" " * 50, end="\r")
                    print(f"\033[92mYou:\033[0m {text}")
                    return text
                except sr.UnknownValueError:
                    print(" " * 50, end="\r")
                    self._set_runtime_state("idle", "Ready")
                    return ""
                except sr.RequestError:
                    print(" " * 50, end="\r")
                    self._set_runtime_state("error", "Speech recognition request failed")
                    return ""

        except sr.WaitTimeoutError:
            print(" " * 50, end="\r")
            self._set_runtime_state("idle", "Ready")
            return ""
        except OSError:
            print(" " * 50, end="\r")
            self._set_runtime_state("needs_permission", "Microphone unavailable")
            return ""
        except Exception:
            print(" " * 50, end="\r")
            self._set_runtime_state("error", "Voice capture failed")
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
                    calcie._handle_wake_ack()
                    # If command came in same wake utterance (e.g. "calcie open youtube"),
                    # execute it directly without forcing a second speech turn.
                    inline_command = (content or "").strip()
                    if inline_command:
                        user_input = inline_command
                        print(f"\033[92mYou:\033[0m {user_input}")
                    else:
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
