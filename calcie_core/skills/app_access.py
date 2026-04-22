"""Skill: deterministic app access commands."""

import json
import html
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import webbrowser
import os
import uuid
from datetime import datetime, timezone
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
            "insta":"https://www.instagram.com",
            "reddit": "https://www.reddit.com",
        }
        self.preferred_media_browser = "chrome"
        self.media_reuse_browser_tabs = (
            os.environ.get("CALCIE_MEDIA_REUSE_BROWSER_TABS", "1").strip().lower()
            in {"1", "true", "yes", "on"}
        )
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
        self.project_root = Path(__file__).resolve().parents[2]
        self.shell_status_path = self.project_root / ".calcie" / "runtime" / "macos_shell_status.json"
        self.media_player_command_path = self.project_root / ".calcie" / "runtime" / "media_player_command.json"
        self.desktop_player_enabled = (
            os.environ.get("CALCIE_DESKTOP_PLAYER_ENABLED", "1").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        try:
            self.desktop_player_shell_max_age_s = float(
                os.environ.get("CALCIE_DESKTOP_PLAYER_SHELL_MAX_AGE_S", "15").strip()
            )
        except ValueError:
            self.desktop_player_shell_max_age_s = 15.0

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
            r"^(?:please\s+)?(?:(?:can|could)\s+you\s+)?(?P<action>play|pause|resume|continue|skip|next|previous|prev|back|restart)\b(?:\s+(?:song|track|video))?\b\s*(?P<body>.*)$",
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

        if self._desktop_player_shell_available():
            player_result = self._handle_play_command_via_calcie_player(action, body)
            if player_result:
                return player_result

        if action in {"skip", "next"}:
            advanced = self._trigger_system_media_command(19)
            if advanced:
                return "Skipping to the next media item..."
            return "Skip is ready in CALCIE Player. Open the player and try again."

        if action in {"previous", "prev", "back"}:
            rewound = self._trigger_system_media_command_repeat(20, repeat=2, delay_s=0.12)
            if rewound:
                return "Going to the previous track..."
            return "Previous is ready in CALCIE Player. Open the player and try again."

        if action == "restart" or (action == "play" and lowered in {"again", "it again", "song again", "track again"}):
            restarted = self._trigger_system_media_command(20)
            if restarted:
                return "Restarting the current track from the beginning..."
            return "Restart is ready in CALCIE Player. Open the player and try again."

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

            # For YouTube desktop app wrappers on macOS, direct watch URLs are often
            # interpreted as plain search text. Use an app-native search sequence first.
            app_play_result = self._play_youtube_query_in_app_macos(search_q)
            if app_play_result:
                return app_play_result

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
        return self._open_media_url(
            "ytmusic",
            url,
            f"YouTube Music: {query}",
            prefer_existing_browser=True,
        )

    def _handle_media_control_command(self, user_input: str) -> Optional[str]:
        raw = (user_input or "").strip()
        if not raw:
            return None

        normalized = re.sub(r"\s+", " ", raw).strip().lower()
        if not self._desktop_player_shell_available():
            return None

        if normalized in {"mute", "mute audio", "mute music"}:
            if self._dispatch_desktop_player_command("mute", show_player=False):
                return "Muting CALCIE Player..."
            return None

        if normalized in {"unmute", "unmute audio", "unmute music"}:
            if self._dispatch_desktop_player_command("unmute", show_player=False):
                return "Unmuting CALCIE Player..."
            return None

        if normalized in {"volume up", "increase volume", "raise volume", "louder"}:
            if self._dispatch_desktop_player_command("volume_up", show_player=False):
                return "Increasing CALCIE Player volume..."
            return None

        if normalized in {"volume down", "decrease volume", "lower volume", "softer"}:
            if self._dispatch_desktop_player_command("volume_down", show_player=False):
                return "Decreasing CALCIE Player volume..."
            return None

        volume_match = re.match(r"^(?:set\s+)?volume(?:\s+to)?\s+(\d{1,3})\s*%?$", normalized)
        if volume_match:
            volume_percent = max(0, min(100, int(volume_match.group(1))))
            if self._dispatch_desktop_player_command(
                "set_volume",
                subtitle=f"{volume_percent}",
                show_player=False,
            ):
                return f"Setting CALCIE Player volume to {volume_percent}%..."
            return None

        if normalized in {"speed up", "faster", "increase speed"}:
            if self._dispatch_desktop_player_command("speed_up", show_player=False):
                return "Increasing CALCIE Player speed..."
            return None

        if normalized in {"slow down", "slower", "decrease speed"}:
            if self._dispatch_desktop_player_command("speed_down", show_player=False):
                return "Decreasing CALCIE Player speed..."
            return None

        speed_match = re.match(
            r"^(?:set\s+)?(?:playback\s+)?speed(?:\s+to)?\s+([0-9]+(?:\.[0-9]+)?)x?$",
            normalized,
        )
        if speed_match:
            speed_value = float(speed_match.group(1))
            speed_value = max(0.25, min(3.0, speed_value))
            if self._dispatch_desktop_player_command(
                "set_speed",
                subtitle=f"{speed_value:.2f}",
                show_player=False,
            ):
                pretty = ("%g" % speed_value)
                return f"Setting CALCIE Player speed to {pretty}x..."
            return None

        seek_forward_match = re.match(
            r"^(?:seek\s+)?(?:forward|skip ahead)\s+(\d{1,3})\s*(?:seconds?|secs?|s)?$",
            normalized,
        )
        if seek_forward_match:
            seconds = max(1, min(600, int(seek_forward_match.group(1))))
            if self._dispatch_desktop_player_command(
                "seek_forward",
                subtitle=str(seconds),
                show_player=False,
            ):
                return f"Seeking forward {seconds} seconds in CALCIE Player..."
            return None

        seek_backward_match = re.match(
            r"^(?:seek\s+)?(?:backward|rewind|back)\s+(\d{1,3})\s*(?:seconds?|secs?|s)?$",
            normalized,
        )
        if seek_backward_match:
            seconds = max(1, min(600, int(seek_backward_match.group(1))))
            if self._dispatch_desktop_player_command(
                "seek_backward",
                subtitle=str(seconds),
                show_player=False,
            ):
                return f"Seeking backward {seconds} seconds in CALCIE Player..."
            return None

        return None

    def _handle_play_command_via_calcie_player(self, action: str, body: str) -> Optional[str]:
        if sys.platform != "darwin" or not self.desktop_player_enabled:
            return None

        lowered = (body or "").strip().lower()
        query = self._clean_media_query(body)

        if action == "pause":
            if self._dispatch_desktop_player_command("pause", show_player=False):
                return "Pausing CALCIE Player..."
            return None

        if action in {"skip", "next"}:
            if self._dispatch_desktop_player_command("next", show_player=False):
                return "Skipping to the next item in CALCIE Player..."
            return None

        if action in {"previous", "prev", "back"}:
            if self._dispatch_desktop_player_command("previous_track", show_player=False):
                return "Going to the previous track in CALCIE Player..."
            return None

        if action == "restart" or (action == "play" and lowered in {"again", "it again", "song again", "track again"}):
            if self._dispatch_desktop_player_command("restart_current", show_player=False):
                return "Restarting the current track in CALCIE Player..."
            return None

        if action in {"resume", "continue"} and (not lowered or "music" in lowered):
            if self._dispatch_desktop_player_command("play", show_player=False):
                return "Resuming CALCIE Player..."
            return None

        if lowered in {"", "music", "songs", "song", "my music", "some music"}:
            if self._dispatch_desktop_player_command("play", show_player=True):
                return "Resuming CALCIE Player..."
            return None

        if lowered in {"youtube", "yt"}:
            if self._dispatch_desktop_player_command(
                "load",
                url="https://www.youtube.com",
                title="YouTube",
                subtitle="Opening YouTube home inside CALCIE Player.",
                platform="youtube",
            ):
                return "Opening YouTube in CALCIE Player..."
            return None

        if lowered in {"youtube music", "ytmusic", "yt music"}:
            if self._dispatch_desktop_player_command(
                "load",
                url="https://music.youtube.com",
                title="YouTube Music",
                subtitle="Opening YouTube Music inside CALCIE Player.",
                platform="ytmusic",
            ):
                return "Opening YouTube Music in CALCIE Player..."
            return None

        target_platform = "ytmusic"
        if re.search(r"\b(video song|video|music video|official video|mv)\b", lowered):
            target_platform = "youtube"
        if re.search(r"\b(?:on|in|using)\s+(youtube|yt)\b", lowered):
            target_platform = "youtube"
        if re.search(r"\b(?:on|in|using)\s+(youtube music|yt music|ytmusic)\b", lowered):
            target_platform = "ytmusic"

        if target_platform == "youtube":
            if not query:
                if self._dispatch_desktop_player_command(
                    "load",
                    url="https://www.youtube.com",
                    title="YouTube",
                    subtitle="Opening YouTube inside CALCIE Player.",
                    platform="youtube",
                ):
                    return "Opening YouTube in CALCIE Player..."
                return None
            search_q = query
            if "official video" not in search_q.lower():
                search_q = f"{search_q} official video"
            watch_url = self._resolve_youtube_watch_url(search_q)
            target_url = watch_url or f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(search_q)}"
            if self._dispatch_desktop_player_command(
                "load",
                url=target_url,
                title=f"YouTube: {query}",
                subtitle="Playing in CALCIE Player via the shared desktop media surface.",
                platform="youtube",
                query=query,
            ):
                return f"Playing {query} in CALCIE Player..."
            return None

        if not query:
            if self._dispatch_desktop_player_command(
                "load",
                url="https://music.youtube.com",
                title="YouTube Music",
                subtitle="Opening YouTube Music inside CALCIE Player.",
                platform="ytmusic",
            ):
                return "Opening YouTube Music in CALCIE Player..."
            return None

        music_watch_url = self._resolve_ytmusic_watch_url(query)
        target_url = music_watch_url or f"https://music.youtube.com/search?q={urllib.parse.quote_plus(query)}"
        if self._dispatch_desktop_player_command(
            "load",
            url=target_url,
            title=f"YouTube Music: {query}",
            subtitle="Playing in CALCIE Player via the shared desktop media surface.",
            platform="ytmusic",
            query=query,
        ):
            return f"Playing {query} in CALCIE Player..."
        return None

    def _desktop_player_shell_available(self) -> bool:
        if sys.platform != "darwin" or not self.desktop_player_enabled:
            return False
        try:
            data = json.loads(self.shell_status_path.read_text(encoding="utf-8"))
        except Exception:
            return False

        if not data.get("player_supported"):
            return False

        updated_at = str(data.get("updated_at") or "").strip()
        if not updated_at:
            return False
        try:
            parsed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()
        return age <= self.desktop_player_shell_max_age_s

    def _dispatch_desktop_player_command(
        self,
        action: str,
        url: Optional[str] = None,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        platform: Optional[str] = None,
        query: Optional[str] = None,
        show_player: bool = True,
    ) -> bool:
        payload = {
            "action": action,
            "request_id": uuid.uuid4().hex,
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "url": url or "",
            "title": title or "",
            "subtitle": subtitle or "",
            "platform": platform or "",
            "query": query or "",
            "show_player": bool(show_player),
        }
        try:
            self.media_player_command_path.parent.mkdir(parents=True, exist_ok=True)
            self.media_player_command_path.write_text(
                json.dumps(payload, ensure_ascii=True),
                encoding="utf-8",
            )
            return True
        except Exception:
            return False

    def _play_youtube_query_in_app_macos(self, query: str) -> Optional[str]:
        if sys.platform != "darwin":
            return None
        if self._media_mode_for_platform("youtube") not in {"app_only", "app_first"}:
            return None

        open_result = self._open_media_url("youtube", "https://www.youtube.com", "YouTube")
        if not open_result.startswith("Opening "):
            return None

        app_match = re.search(r"\bin\s+(.+?)\s+app\.\.\.$", open_result, flags=re.IGNORECASE)
        if not app_match:
            # Not app mode (likely browser path), let caller continue with URL flow.
            return None
        app_name = app_match.group(1).strip()
        if not app_name:
            return None

        ok = self._youtube_app_search_and_open_first_macos(app_name, query)
        if not ok:
            return None
        return f"Opening YouTube and playing {query}..."

    def _youtube_app_search_and_open_first_macos(self, app_name: str, query: str) -> bool:
        if sys.platform != "darwin":
            return False
        escaped_app = self._escape_applescript(app_name)
        escaped_query = self._escape_applescript(query)
        script = (
            f'tell application "{escaped_app}" to activate\n'
            "delay 0.45\n"
            'tell application "System Events"\n'
            "key code 53\n"  # ESC: close shortcuts/dialog if present
            "delay 0.08\n"
            "key code 53\n"
            "delay 0.08\n"
            'keystroke "/"\n'  # focus YouTube search
            "delay 0.12\n"
            f'keystroke "{escaped_query}"\n'
            "key code 36\n"  # Enter to search
            "delay 1.15\n"
            "key code 48\n"  # Tab to first result focus region
            "delay 0.08\n"
            "key code 36\n"  # Enter first result
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

        if (
            self.media_reuse_browser_tabs
            and sys.platform == "darwin"
            and media_mode != "app_only"
            and self._open_media_url_in_existing_browser_surface_macos(platform, url)
        ):
            browser_name = self.app_commands.get(self.preferred_media_browser, self.preferred_media_browser)
            return f"Opening {label} in {browser_name}..."

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

        candidates = self._extract_ranked_youtube_candidates(html, query)
        if candidates:
            return f"https://www.youtube.com/watch?v={candidates[0]['video_id']}&autoplay=1"

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

    def _extract_ranked_youtube_candidates(self, html_text: str, query: str) -> list:
        candidates = []
        seen = set()
        query_terms = self._media_query_terms(query)
        pattern = re.compile(
            r'"videoId":"(?P<video_id>[A-Za-z0-9_-]{11})".{0,900}?"title":\{"runs":\[\{"text":"(?P<title>.*?)"\}\]',
            flags=re.DOTALL,
        )

        for match in pattern.finditer(html_text):
            video_id = match.group("video_id")
            if video_id in seen:
                continue
            seen.add(video_id)
            raw_title = match.group("title") or ""
            title = html.unescape(raw_title).replace("\\u0026", "&").replace('\\"', '"').strip()
            score = self._score_youtube_candidate(query_terms, title)
            candidates.append(
                {
                    "video_id": video_id,
                    "title": title,
                    "score": score,
                }
            )

        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates

    def _media_query_terms(self, query: str) -> list:
        lowered = (query or "").lower()
        lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
        terms = [term for term in lowered.split() if len(term) > 1]
        return terms

    def _score_youtube_candidate(self, query_terms: list, title: str) -> int:
        lowered_title = (title or "").lower()
        score = 0

        for term in query_terms:
            if lowered_title == term:
                score += 8
            elif lowered_title.startswith(term + " "):
                score += 6
            elif re.search(rf"\b{re.escape(term)}\b", lowered_title):
                score += 4
            elif term in lowered_title:
                score += 2

        phrase = " ".join(query_terms).strip()
        if phrase:
            if phrase == lowered_title:
                score += 24
            elif phrase in lowered_title:
                score += 12

        quality_hints = {
            "official video": 10,
            "official music video": 10,
            "lyric video": 3,
            "audio": 2,
            "topic": 1,
            "live": -2,
            "reaction": -8,
            "cover": -6,
            "karaoke": -8,
            "slowed": -5,
            "reverb": -5,
            "remix": -4,
            "8d": -8,
            "shorts": -4,
        }
        for hint, weight in quality_hints.items():
            if hint in lowered_title:
                score += weight

        return score

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

        # Non-browser app wrappers (e.g., YouTube app) should not receive URL keystrokes.
        # Typing a URL containing "?" into page context can open YouTube shortcuts modal.
        if not self._supports_keyboard_url_navigation_macos(app_name):
            return self.open_target_in_app(url, app_name, allow_default_browser_fallback=False)

        # Reuse running browser window first to avoid new instances.
        if self._is_app_running_macos(app_name):
            if self._navigate_url_in_front_app_macos(app_name, url):
                return f"Opening {url} in {app_name}..."

        # Start browser (or bring to front) without URL payload, then navigate within app window.
        started_ok, opened_as, _ = self._open_app_macos(app_name)
        if started_ok:
            target_name = opened_as or app_name
            if self._navigate_url_in_front_app_macos(target_name, url):
                return f"Opening {url} in {target_name}..."

        # Last resort for browsers/wrappers that accept URL arguments.
        return self.open_target_in_app(url, app_name, allow_default_browser_fallback=False)

    def _navigate_url_in_front_app_macos(self, app_name: str, url: str) -> bool:
        if sys.platform != "darwin":
            return False
        if not self._supports_keyboard_url_navigation_macos(app_name):
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

    def _supports_keyboard_url_navigation_macos(self, app_name: str) -> bool:
        lowered = (app_name or "").strip().lower()
        return lowered in {
            "google chrome",
            "chrome",
            "safari",
            "firefox",
            "microsoft edge",
            "edge",
        }

    def _media_domains(self, platform: str) -> list:
        key = (platform or "").strip().lower()
        if key == "ytmusic":
            return ["music.youtube.com"]
        if key == "youtube":
            return ["youtube.com", "www.youtube.com"]
        return []

    def _open_media_url_in_existing_browser_surface_macos(self, platform: str, url: str) -> bool:
        if sys.platform != "darwin":
            return False
        browser_name = self.app_commands.get(self.preferred_media_browser, self.preferred_media_browser)
        if not self._is_app_running_macos(browser_name):
            return False

        domains = self._media_domains(platform)
        if not domains:
            return False

        escaped_url = self._escape_applescript(url)
        lowered = browser_name.strip().lower()

        if lowered == "google chrome":
            domain_checks = " or ".join(
                [f'((URL of t as text) contains "{self._escape_applescript(domain)}")' for domain in domains]
            ) or "false"
            script = (
                'tell application "Google Chrome"\n'
                "activate\n"
                "if (count of windows) = 0 then make new window\n"
                "set foundTab to false\n"
                "repeat with w in windows\n"
                "repeat with t in tabs of w\n"
                f"if {domain_checks} then\n"
                "set active tab index of w to (index of t)\n"
                "set index of w to 1\n"
                f'set URL of t to "{escaped_url}"\n'
                "set foundTab to true\n"
                "exit repeat\n"
                "end if\n"
                "end repeat\n"
                "if foundTab then exit repeat\n"
                "end repeat\n"
                "if not foundTab then\n"
                'tell front window to make new tab with properties {URL:"'
                + escaped_url
                + '"}\n'
                "end if\n"
                "end tell"
            )
        elif lowered == "safari":
            domain_checks = " or ".join(
                [f'((URL of t as text) contains "{self._escape_applescript(domain)}")' for domain in domains]
            ) or "false"
            script = (
                'tell application "Safari"\n'
                "activate\n"
                "if (count of windows) = 0 then make new document\n"
                "set foundTab to false\n"
                "repeat with w in windows\n"
                "repeat with t in tabs of w\n"
                f"if {domain_checks} then\n"
                "set current tab of w to t\n"
                f'set URL of t to "{escaped_url}"\n'
                "set index of w to 1\n"
                "set foundTab to true\n"
                "exit repeat\n"
                "end if\n"
                "end repeat\n"
                "if foundTab then exit repeat\n"
                "end repeat\n"
                "if not foundTab then\n"
                'tell front window to set current tab to (make new tab with properties {URL:"'
                + escaped_url
                + '"})\n'
                "end if\n"
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

    def _trigger_system_media_command(self, key_code: int) -> bool:
        if sys.platform != "darwin":
            return False
        try:
            proc = subprocess.run(
                ["osascript", "-e", f'tell application "System Events" to key code {key_code}'],
                capture_output=True,
                text=True,
            )
            return proc.returncode == 0
        except Exception:
            return False

    def _trigger_system_media_command_repeat(self, key_code: int, repeat: int = 2, delay_s: float = 0.12) -> bool:
        if sys.platform != "darwin":
            return False
        try:
            repeat = max(1, int(repeat))
            script_lines = ['tell application "System Events"']
            for index in range(repeat):
                script_lines.append(f"key code {int(key_code)}")
                if index < repeat - 1:
                    script_lines.append(f"delay {float(delay_s):.2f}")
            script_lines.append("end tell")
            proc = subprocess.run(
                ["osascript", "-e", "\n".join(script_lines)],
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

        media_control_result = self._handle_media_control_command(user_input)
        if media_control_result is not None:
            return media_control_result, media_control_result

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
