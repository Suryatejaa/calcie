"""Skill: deterministic app access commands."""

import re
import subprocess
import sys
import urllib.parse
import urllib.request
import webbrowser
import os
from pathlib import Path
from typing import Dict, Optional, Tuple


class AppAccessSkill:
    def __init__(self, app_aliases: Dict[str, str]):
        self.app_aliases = dict(app_aliases)
        self.app_commands = {
            "chrome": "Google Chrome",
            "safari": "Safari",
            "firefox": "Firefox",
            "terminal": "Terminal",
            "finder": "Finder",
            "notes": "Notes",
            "calendar": "Calendar",
            "mail": "Mail",
            "music": "Music",
            "spotify": "Spotify",
            "vscode": "Visual Studio Code",
            "slack": "Slack",
            "discord": "Discord",
            "voice memos": "Voice Memos",
            "voicememos": "VoiceMemos",
            "youtube music": "YouTube Music",
            "yt music": "YouTube Music",
            "ytmusic": "YouTube Music",
            "youtube": "YouTube",
            "yt": "YouTube",
        }
        self.web_aliases = {
            "amazon": "https://www.amazon.com",
            "youtube": "https://www.youtube.com",
            "gmail": "https://mail.google.com",
            "google": "https://www.google.com",
            "github": "https://github.com",
            "chatgpt": "https://chatgpt.com",
            "linkedin": "https://www.linkedin.com",
            "twitter": "https://x.com",
            "x": "https://x.com",
            "instagram": "https://www.instagram.com",
            "reddit": "https://www.reddit.com",
        }
        self.preferred_media_browser = "chrome"
        self.media_open_mode = (os.environ.get("CALCIE_MEDIA_OPEN_MODE") or "app_first").strip().lower()
        if self.media_open_mode not in {"app_first", "browser_only"}:
            self.media_open_mode = "app_first"
        self.youtube_open_mode = self._normalize_media_mode(
            os.environ.get("CALCIE_YOUTUBE_OPEN_MODE"),
            default=self.media_open_mode,
        )
        self.ytmusic_open_mode = self._normalize_media_mode(
            os.environ.get("CALCIE_YTMUSIC_OPEN_MODE"),
            default=self.media_open_mode,
        )
        self.media_apps = self._build_media_app_preferences()
        self.bundle_ids = {
            "voice memos": "com.apple.VoiceMemos",
            "google chrome": "com.google.Chrome",
            "safari": "com.apple.Safari",
            "firefox": "org.mozilla.firefox",
            "visual studio code": "com.microsoft.VSCode",
            "spotify": "com.spotify.client",
            "youtube music": "com.google.Chrome.app.aeblfdkhhhdcdjpifhhbdiojplfjncoa",
            "youtube": "com.google.Chrome.app.agimnkijcaahngcdmfeangaknmldooml",
        }

    def extract_open_app_command(self, user_input: str) -> Optional[str]:
        raw = (user_input or "").strip()
        if not raw:
            return None

        lowered = raw.lower()
        normalized = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", lowered)).strip()
        if not normalized:
            return None

        if normalized in self.app_aliases:
            return self.app_aliases[normalized]

        match = re.match(
            r"^(?:please\s+)?(?:(?:can|could)\s+you\s+)?(?:open|launch|start)\s+(?:the\s+|a\s+|an\s+)?(.+)$",
            normalized,
        )
        if not match:
            return None

        target = match.group(1).strip()
        if not target or target in {"a", "an", "the"}:
            return None
        if target in self.app_aliases:
            return self.app_aliases[target]

        for alias in sorted(self.app_aliases.keys(), key=len, reverse=True):
            if re.search(rf"\b{re.escape(alias)}\b", target):
                return self.app_aliases[alias]

        if len(target.split()) <= 3:
            return target
        return None

    def looks_like_open_app_intent(self, user_input: str) -> bool:
        raw = (user_input or "").strip().lower()
        if not raw:
            return False
        return bool(
            re.match(
                r"^(?:please\s+)?(?:(?:can|could)\s+you\s+)?(?:open|launch|start)\b",
                raw,
            )
        )

    def open_app(self, app_name: str) -> str:
        app_lower = (app_name or "").strip().lower()
        if not app_lower:
            return "Tell me the app name. Example: 'open chrome'."

        app_target = self.app_commands.get(app_lower, app_name.strip())
        try:
            if sys.platform == "darwin":
                ok, opened_as, err = self._open_app_macos(app_target)
                if ok:
                    return f"Opening {opened_as}..."
                return f"Failed to open {app_target}: {err}"
            if sys.platform.startswith("linux"):
                subprocess.Popen([app_lower], start_new_session=True)
                return f"Opening {app_target}..."
            return "App opening is not supported on this platform."
        except Exception as exc:
            return f"Failed to open {app_target}: {exc}"

    def open_target_in_app(self, target: str, app_name: str, allow_default_browser_fallback: bool = True) -> str:
        target = (target or "").strip()
        app_name = (app_name or "").strip()
        if not target or not app_name:
            return "Usage: open <target> in <app>"

        app_lower = app_name.lower()
        app_target = self.app_commands.get(app_lower, app_name)
        url = self._normalize_target_to_url(target)

        try:
            if sys.platform == "darwin":
                candidates = self._macos_app_candidates(app_target)
                last_err = "Application not found."
                for candidate in candidates:
                    proc = subprocess.run(
                        ["open", "-a", candidate, url],
                        capture_output=True,
                        text=True,
                    )
                    if proc.returncode == 0:
                        return f"Opening {target} in {candidate}..."
                    err = (proc.stderr or proc.stdout or "").strip()
                    if err and last_err == "Application not found.":
                        last_err = err

                bundle_id = self._bundle_id_for_app(app_target)
                if bundle_id:
                    proc = subprocess.run(
                        ["open", "-b", bundle_id, url],
                        capture_output=True,
                        text=True,
                    )
                    if proc.returncode == 0:
                        return f"Opening {target} in {app_target}..."
                    err = (proc.stderr or proc.stdout or "").strip()
                    if err and last_err == "Application not found.":
                        last_err = err

                # Browser fallback: if target app is missing, still open URL in default browser.
                if allow_default_browser_fallback and self._open_url_default_macos(url):
                    return f"Could not find {app_target}. Opened {target} in the default browser."
                return f"Failed to open {target} in {app_target}: {last_err}"

            if sys.platform.startswith("linux"):
                try:
                    subprocess.Popen([app_lower, url], start_new_session=True)
                    return f"Opening {target} in {app_target}..."
                except Exception:
                    if allow_default_browser_fallback and self._open_url_default_linux(url):
                        return f"Could not find {app_target}. Opened {target} in the default browser."
                    raise

            return "Open target in app is not supported on this platform."
        except Exception as exc:
            return f"Failed to open {target} in {app_target}: {exc}"

    def _open_app_macos(self, app_target: str):
        """Try robust macOS app resolution for names with/without spaces."""
        candidates = self._macos_app_candidates(app_target)
        last_err = "Application not found."
        for candidate in candidates:
            proc = subprocess.run(
                ["open", "-a", candidate],
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                return True, candidate, ""
            err = (proc.stderr or proc.stdout or "").strip()
            if err and last_err == "Application not found.":
                last_err = err

        bundle_id = self._bundle_id_for_app(app_target)
        if bundle_id:
            proc = subprocess.run(
                ["open", "-b", bundle_id],
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                return True, app_target, ""
            err = (proc.stderr or proc.stdout or "").strip()
            if err and last_err == "Application not found.":
                last_err = err

        return False, app_target, last_err

    def _macos_app_candidates(self, app_target: str):
        candidates = []
        raw = (app_target or "").strip()
        if raw:
            candidates.append(raw)

        titled = raw.title()
        if titled and titled not in candidates:
            candidates.append(titled)

        compact = raw.replace(" ", "")
        if compact and compact not in candidates:
            candidates.append(compact)

        if raw.lower() == "voice memos":
            for item in ["VoiceMemos", "Voice Memos"]:
                if item not in candidates:
                    candidates.append(item)

        return candidates

    def _bundle_id_for_app(self, app_target: str) -> Optional[str]:
        key = (app_target or "").strip().lower()
        return self.bundle_ids.get(key)

    def _open_url_default_macos(self, url: str) -> bool:
        if sys.platform != "darwin":
            return False
        try:
            proc = subprocess.run(
                ["open", url],
                capture_output=True,
                text=True,
            )
            return proc.returncode == 0
        except Exception:
            return False

    def _open_url_default_linux(self, url: str) -> bool:
        if not sys.platform.startswith("linux"):
            return False
        try:
            proc = subprocess.run(
                ["xdg-open", url],
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                return True
        except Exception:
            pass
        try:
            return bool(webbrowser.open(url))
        except Exception:
            return False

    def _extract_open_target_in_app_command(self, user_input: str) -> Optional[Tuple[str, str]]:
        raw = (user_input or "").strip()
        if not raw:
            return None

        # Keep punctuation for URL-ish targets; normalize only whitespace.
        compact = re.sub(r"\s+", " ", raw).strip()
        match = re.match(
            r"^(?:please\s+)?(?:(?:can|could)\s+you\s+)?(?:open|launch|start)\s+(.+?)\s+(?:in|on|using|with)\s+(.+)$",
            compact,
            flags=re.IGNORECASE,
        )
        if not match:
            return None

        target = match.group(1).strip(" \"'")
        app_part = match.group(2).strip(" \"'").lower()
        if not target or not app_part:
            return None

        app_alias = self.app_aliases.get(app_part)
        if app_alias:
            return target, app_alias

        for alias in sorted(self.app_aliases.keys(), key=len, reverse=True):
            if re.search(rf"\b{re.escape(alias)}\b", app_part):
                return target, self.app_aliases[alias]

        # Fall back to raw app name (user might say full app title).
        return target, app_part

    def _extract_play_command(self, user_input: str) -> Optional[Tuple[str, str]]:
        raw = (user_input or "").strip()
        if not raw:
            return None
        compact = re.sub(r"\s+", " ", raw).strip()
        match = re.match(
            r"^(?:please\s+)?(?:(?:can|could)\s+you\s+)?(?P<action>play|resume|continue)\b\s*(?P<body>.*)$",
            compact,
            flags=re.IGNORECASE,
        )
        if not match:
            return None

        action = (match.group("action") or "play").strip().lower()
        body = (match.group("body") or "").strip(" \"'")
        return action, body

    def _handle_play_command(self, user_input: str) -> Optional[str]:
        parsed = self._extract_play_command(user_input)
        if not parsed:
            return None

        action, body = parsed
        lowered = body.lower()

        # OTT intentionally deferred for now.
        ott_markers = ["netflix", "prime", "prime video", "hotstar", "disney", "zee5", "sony liv", "jio cinema"]
        if any(k in lowered for k in ott_markers):
            return "OTT play flow is not enabled yet. For now I can play on YouTube Music or YouTube."

        if "movie" in lowered and not any(k in lowered for k in ["youtube", "yt", "video song"]):
            return "Movie-on-OTT flow is next phase. For now, say: play <song> or play video song <name>."

        if action in {"resume", "continue"} and (not lowered or "music" in lowered):
            return self._resume_youtube_music()

        if lowered in {"", "music", "songs", "song", "my music", "some music"}:
            return self._resume_youtube_music()

        if lowered in {"youtube", "yt"}:
            return self._open_media_url("youtube", "https://www.youtube.com", "YouTube")
        if lowered in {"youtube music", "ytmusic", "yt music"}:
            return self._resume_youtube_music()

        target_platform = "ytmusic"  # default requirement: always prefer YouTube Music
        if re.search(r"\b(video song|video|music video|official video|mv)\b", lowered):
            target_platform = "youtube"
        if re.search(r"\b(?:on|in|using)\s+(youtube|yt)\b", lowered):
            target_platform = "youtube"
        if re.search(r"\b(?:on|in|using)\s+(youtube music|yt music|ytmusic)\b", lowered):
            target_platform = "ytmusic"

        query = self._clean_media_query(body)
        if target_platform == "youtube":
            if not query:
                return self._open_media_url("youtube", "https://www.youtube.com", "YouTube")
            search_q = query
            if "official video" not in search_q.lower():
                search_q = f"{search_q} official video"
            watch_url = self._resolve_youtube_watch_url(search_q)
            if watch_url:
                return self._open_media_url(
                    "youtube",
                    watch_url,
                    f"YouTube: {query}",
                    prefer_existing_browser=True,
                )
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(search_q)}"
            return self._open_media_url(
                "youtube",
                url,
                f"YouTube: {query}",
                prefer_existing_browser=True,
            )

        # Default route: YouTube Music
        if not query:
            return self._resume_youtube_music()
        music_watch_url = self._resolve_ytmusic_watch_url(query)
        if music_watch_url:
            return self._open_media_url(
                "ytmusic",
                music_watch_url,
                f"YouTube Music: {query}",
                prefer_existing_browser=True,
            )
        url = f"https://music.youtube.com/search?q={urllib.parse.quote_plus(query)}"
        return self._open_media_url("ytmusic", url, f"YouTube Music: {query}")

    def _clean_media_query(self, body: str) -> str:
        text = (body or "").strip()
        if not text:
            return ""
        # remove platform qualifiers
        patterns = [
            r"\b(?:on|in|using)\s+(youtube music|yt music|ytmusic)\b",
            r"\b(?:on|in|using)\s+(youtube|yt)\b",
            r"\b(video song|music video|official video|video|song)\b",
        ]
        lowered = text.lower()
        for pat in patterns:
            lowered = re.sub(pat, " ", lowered, flags=re.IGNORECASE)
        lowered = re.sub(r"\s+", " ", lowered).strip(" ,.-")
        lowered = re.sub(r"^(?:of|for|the)\s+", "", lowered).strip()
        return lowered

    def _open_url_in_browser(self, url: str, label: str, reuse_existing_tab: bool = False) -> str:
        if reuse_existing_tab and sys.platform == "darwin":
            if self._open_url_in_existing_browser_tab_macos(url):
                browser_name = self.app_commands.get(self.preferred_media_browser, self.preferred_media_browser)
                return f"Opening {label} in {browser_name}..."

        result = self.open_target_in_app(url, self.preferred_media_browser)
        if result.startswith("Opening "):
            browser_name = self.app_commands.get(self.preferred_media_browser, self.preferred_media_browser)
            return f"Opening {label} in {browser_name}..."
        if result.startswith("Could not find "):
            return f"Opening {label} in the default browser (preferred browser unavailable)."
        return result

    def _open_media_url(
        self,
        platform: str,
        url: str,
        label: str,
        prefer_existing_browser: bool = False,
    ) -> str:
        """Open media URL with per-platform mode (app_only/app_first/browser_only)."""
        media_mode = self._media_mode_for_platform(platform)

        if prefer_existing_browser and media_mode != "app_only":
            reused = self._open_url_in_browser(url, label, reuse_existing_tab=True)
            if reused.startswith("Opening "):
                return reused

        if media_mode in {"app_only", "app_first"} and sys.platform == "darwin":
            for app_name in self._media_app_candidates(platform):
                result = self._open_url_in_app_window_macos(app_name, url)
                if result.startswith("Opening "):
                    return f"Opening {label} in {app_name} app..."

        if media_mode == "app_only":
            return (
                f"Could not open {label} in YouTube app mode. "
                "Set CALCIE_YOUTUBE_APP_NAME/CALCIE_YTMUSIC_APP_NAME to your installed app name."
            )

        return self._open_url_in_browser(url, label)

    def _normalize_media_mode(self, raw_value: Optional[str], default: str) -> str:
        value = (raw_value or "").strip().lower()
        if value in {"app_only", "app_first", "browser_only"}:
            return value
        return default

    def _media_mode_for_platform(self, platform: str) -> str:
        key = (platform or "").strip().lower()
        if key == "youtube":
            return self.youtube_open_mode
        if key == "ytmusic":
            return self.ytmusic_open_mode
        return self.media_open_mode

    def _resolve_youtube_watch_url(self, query: str) -> Optional[str]:
        search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
        req = urllib.request.Request(
            search_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"
                )
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                html = res.read(800_000).decode("utf-8", errors="replace")
        except Exception:
            return None

        seen = set()
        for vid in re.findall(r"\"videoId\":\"([a-zA-Z0-9_-]{11})\"", html):
            if vid in seen:
                continue
            seen.add(vid)
            return f"https://www.youtube.com/watch?v={vid}&autoplay=1"
        return None

    def _resolve_ytmusic_watch_url(self, query: str) -> Optional[str]:
        video_url = self._resolve_youtube_watch_url(query)
        if not video_url:
            return None
        match = re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", video_url)
        if not match:
            return None
        vid = match.group(1)
        return f"https://music.youtube.com/watch?v={vid}&autoplay=1"

    def _escape_applescript(self, text: str) -> str:
        return (text or "").replace("\\", "\\\\").replace('"', '\\"')

    def _is_app_running_macos(self, app_name: str) -> bool:
        if sys.platform != "darwin":
            return False
        escaped = self._escape_applescript(app_name)
        script = f'tell application "System Events" to (name of processes) contains "{escaped}"'
        try:
            proc = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
            )
            return proc.returncode == 0 and proc.stdout.strip().lower() == "true"
        except Exception:
            return False

    def _open_url_in_existing_browser_tab_macos(self, url: str) -> bool:
        if sys.platform != "darwin":
            return False
        browser_name = self.app_commands.get(self.preferred_media_browser, self.preferred_media_browser)
        if not self._is_app_running_macos(browser_name):
            return False

        escaped_url = self._escape_applescript(url)
        lowered = browser_name.strip().lower()

        if lowered == "google chrome":
            script = (
                'tell application "Google Chrome"\n'
                "activate\n"
                "if (count of windows) = 0 then\n"
                "make new window\n"
                "end if\n"
                f'set URL of active tab of front window to "{escaped_url}"\n'
                "end tell"
            )
        elif lowered == "safari":
            script = (
                'tell application "Safari"\n'
                "activate\n"
                "if (count of windows) = 0 then\n"
                "make new document\n"
                "end if\n"
                f'set URL of current tab of front window to "{escaped_url}"\n'
                "end tell"
            )
        else:
            return False

        try:
            proc = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
            )
            return proc.returncode == 0
        except Exception:
            return False

    def _open_url_in_app_window_macos(self, app_name: str, url: str) -> str:
        if sys.platform != "darwin":
            return "App-window URL routing is only supported on macOS."

        # Reuse running app window first to avoid new instances.
        if self._is_app_running_macos(app_name):
            if self._navigate_url_in_front_app_macos(app_name, url):
                return f"Opening {url} in {app_name}..."

        # Start app (or bring to front) without URL payload, then navigate within app window.
        started_ok, opened_as, _ = self._open_app_macos(app_name)
        if started_ok:
            target_name = opened_as or app_name
            if self._navigate_url_in_front_app_macos(target_name, url):
                return f"Opening {url} in {target_name}..."

        # Last resort for app wrappers that accept URL arguments.
        return self.open_target_in_app(url, app_name, allow_default_browser_fallback=False)

    def _navigate_url_in_front_app_macos(self, app_name: str, url: str) -> bool:
        if sys.platform != "darwin":
            return False

        escaped_app = self._escape_applescript(app_name)
        escaped_url = self._escape_applescript(url)
        script = (
            f'tell application "{escaped_app}" to activate\n'
            "delay 0.18\n"
            'tell application "System Events"\n'
            'keystroke "l" using {command down}\n'
            "delay 0.08\n"
            f'keystroke "{escaped_url}"\n'
            "key code 36\n"
            "end tell"
        )
        try:
            proc = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
            )
            return proc.returncode == 0
        except Exception:
            return False

    def _resume_youtube_music(self) -> str:
        open_result = self._open_media_url("ytmusic", "https://music.youtube.com", "YouTube Music")
        if not open_result.startswith("Opening "):
            return open_result

        resumed = self._trigger_system_play_pause()
        if resumed:
            return "Opening YouTube Music and resuming playback..."
        return "Opening YouTube Music. If playback was paused, press play once."

    def _trigger_system_play_pause(self) -> bool:
        if sys.platform != "darwin":
            return False
        try:
            proc = subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to key code 16'],
                capture_output=True,
                text=True,
            )
            return proc.returncode == 0
        except Exception:
            return False

    def _build_media_app_preferences(self) -> Dict[str, list]:
        ytm_custom = (os.environ.get("CALCIE_YTMUSIC_APP_NAME") or "").strip()
        yt_custom = (os.environ.get("CALCIE_YOUTUBE_APP_NAME") or "").strip()

        ytm_defaults = ["YouTube Music", "YouTubeMusic", "YTMusic"]
        yt_defaults = ["YouTube"]
        ytm_discovered = self._discover_macos_app_names(["youtube music", "ytmusic", "yt music"])
        yt_discovered = self._discover_macos_app_names(["youtube"], exclude_tokens=["music"])

        ytm_apps = []
        yt_apps = []
        if ytm_custom:
            ytm_apps.append(ytm_custom)
        if yt_custom:
            yt_apps.append(yt_custom)
        ytm_apps.extend(ytm_discovered)
        yt_apps.extend(yt_discovered)
        ytm_apps.extend(ytm_defaults)
        yt_apps.extend(yt_defaults)

        return {
            "ytmusic": self._dedupe_keep_order(ytm_apps),
            "youtube": self._dedupe_keep_order(yt_apps),
        }

    def _media_app_candidates(self, platform: str) -> list:
        key = (platform or "").strip().lower()
        return list(self.media_apps.get(key, []))

    def _dedupe_keep_order(self, items: list) -> list:
        seen = set()
        out = []
        for item in items:
            value = (item or "").strip()
            if not value:
                continue
            lowered = value.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            out.append(value)
        return out

    def _discover_macos_app_names(self, tokens: list, exclude_tokens: Optional[list] = None) -> list:
        if sys.platform != "darwin":
            return []
        exclude_tokens = exclude_tokens or []
        roots = [Path("/Applications"), Path.home() / "Applications"]
        discovered = []
        for root in roots:
            try:
                if not root.exists():
                    continue
                for entry in root.iterdir():
                    if not entry.is_dir():
                        continue
                    name = entry.name
                    if not name.lower().endswith(".app"):
                        continue
                    app_name = name[:-4]
                    lowered = app_name.lower()
                    if not any(t in lowered for t in tokens):
                        continue
                    if any(t in lowered for t in exclude_tokens):
                        continue
                    discovered.append(app_name)
            except Exception:
                continue
        return self._dedupe_keep_order(discovered)

    def _normalize_target_to_url(self, target: str) -> str:
        raw = (target or "").strip()
        lowered = raw.lower()
        if not raw:
            return "https://www.google.com"

        if lowered in self.web_aliases:
            return self.web_aliases[lowered]

        if re.match(r"^https?://", raw, flags=re.IGNORECASE):
            return raw

        if raw.startswith("www."):
            return f"https://{raw}"

        # Domain-like token
        if " " not in raw and "." in raw:
            return f"https://{raw}"

        # Fallback: search query so commands like "open latest ai news in chrome" work.
        encoded = urllib.parse.quote_plus(raw)
        return f"https://www.google.com/search?q={encoded}"

    def handle_command(self, user_input: str) -> Tuple[Optional[str], Optional[str]]:
        play_result = self._handle_play_command(user_input)
        if play_result is not None:
            return play_result, play_result

        target_in_app = self._extract_open_target_in_app_command(user_input)
        if target_in_app:
            target, app = target_in_app
            result = self.open_target_in_app(target, app)
            return result, result

        app_to_open = self.extract_open_app_command(user_input)
        if app_to_open:
            result = self.open_app(app_to_open)
            return result, result

        if self.looks_like_open_app_intent(user_input):
            prompt = "Tell me the app name. Example: 'open chrome' or just 'chrome'."
            return prompt, "Tell me the app name."

        return None, None
