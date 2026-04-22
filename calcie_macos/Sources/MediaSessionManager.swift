import AppKit
import SwiftUI
import WebKit

private struct PersistedMediaSessionState: Codable {
    let currentURLString: String
    let lastPlayableURLString: String
    let lastPlayableTitle: String
    let currentPlatform: String
    let lastResolvedQuery: String
    let lastCommandAction: String
    let recentHistory: [PersistedMediaHistoryItem]
    let currentHistoryIndex: Int?
}

private struct PersistedMediaHistoryItem: Codable {
    let url: String
    let title: String
    let platform: String
    let query: String
}

struct MediaPlayerCommandRequest: Decodable {
    let action: String
    let request_id: String?
    let requested_at: String?
    let url: String?
    let title: String?
    let subtitle: String?
    let platform: String?
    let query: String?
    let show_player: Bool?
}

struct MediaHistoryItem: Identifiable, Equatable {
    let id = UUID()
    let url: String
    let title: String
    let platform: String
    let query: String
}

@MainActor
final class MediaSessionManager: NSObject, ObservableObject, WKNavigationDelegate {
    @Published var playerSurfaceState = "idle"
    @Published var currentTitle = "No media loaded"
    @Published var currentSubtitle = "Phase 1 player surface is ready."
    @Published var currentURLString = ""
    @Published var lastPlayableURLString = ""
    @Published var lastPlayableTitle = ""
    @Published var currentPlatform = "unknown"
    @Published var lastResolvedQuery = ""
    @Published var lastCommandAction = ""
    @Published var recentHistory: [MediaHistoryItem] = []
    @Published var currentHistoryIndex: Int? = nil
    @Published var googleSessionState = "unknown"
    @Published var googleSessionDetail = "Google session not checked yet."
    @Published var googleSessionFallbackHint = "Use Premium Login in Player when you need YouTube Premium/ad-free playback inside CALCIE Player."

    private(set) var playerPanel: NSPanel?
    private(set) var webView: WKWebView?
    private let bootstrapURL = URL(string: "https://youtu.be/k9_JbEaRxso?si=g1_5TZICdj_XBgsd")!
    private let sessionStateURL: URL
    private let websiteDataStore: WKWebsiteDataStore
    private var allowEmbeddedGoogleLogin = false

    override init() {
        let runtimeDir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".calcie/runtime", isDirectory: true)
        self.sessionStateURL = runtimeDir.appendingPathComponent("media_session_state.json")
        self.websiteDataStore = WKWebsiteDataStore.default()
        super.init()
        loadPersistedSessionState()
        refreshGoogleSessionStatus()
    }

    func showPlayer() {
        ensurePlayerSurface()
        if currentURLString.isEmpty {
            if !loadLastPlayableMediaIfAvailable() {
                loadBootstrapMedia()
            }
        }
        playerPanel?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func loadBootstrapMedia() {
        ensurePlayerSurface()
        let request = URLRequest(url: bootstrapURL)
        webView?.load(request)
        currentTitle = "CALCIE Player"
        currentSubtitle = "Bootstrap player loaded with a regular YouTube watch page so WKWebView can render it reliably."
        currentURLString = bootstrapURL.absoluteString
        playerSurfaceState = "loading"
    }

    func reloadCurrentMedia() {
        ensurePlayerSurface()
        if let url = URL(string: currentURLString), !currentURLString.isEmpty {
            webView?.load(URLRequest(url: url))
            playerSurfaceState = "loading"
            return
        }
        if loadLastPlayableMediaIfAvailable() {
            return
        }
        loadBootstrapMedia()
    }

    func openGoogleSignIn(for platform: String = "youtube") {
        let normalizedPlatform = platform == "ytmusic" ? "ytmusic" : "youtube"
        currentPlatform = normalizedPlatform
        currentTitle = normalizedPlatform == "ytmusic" ? "YouTube Music Sign-In" : "YouTube Sign-In"
        currentSubtitle = "Google sign-in opens in your browser so you do not enter your password inside CALCIE Player."
        googleSessionState = "signing_in"
        googleSessionDetail = "Opened Google sign-in in your default browser. Return here after you finish login."
        openGoogleSignInInBrowser(for: normalizedPlatform)
    }

    func openProviderHome(_ platform: String) {
        ensurePlayerSurface()
        let normalizedPlatform = platform == "ytmusic" ? "ytmusic" : "youtube"
        let urlString = normalizedPlatform == "ytmusic" ? "https://music.youtube.com/" : "https://www.youtube.com/"
        guard let url = URL(string: urlString) else { return }
        currentPlatform = normalizedPlatform
        currentTitle = normalizedPlatform == "ytmusic" ? "YouTube Music" : "YouTube"
        currentSubtitle = "Opening your signed-in \(normalizedPlatform == "ytmusic" ? "YouTube Music" : "YouTube") session in CALCIE Player."
        currentURLString = url.absoluteString
        playerSurfaceState = "loading"
        playerPanel?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        webView?.load(URLRequest(url: url))
    }

    func openGoogleSignInInBrowser(for platform: String = "youtube") {
        let normalizedPlatform = platform == "ytmusic" ? "ytmusic" : "youtube"
        let continueURL = normalizedPlatform == "ytmusic"
            ? "https://music.youtube.com/"
            : "https://www.youtube.com/"
        guard
            let signInURL = URL(
                string: "https://accounts.google.com/ServiceLogin?service=youtube&continue=\(continueURL.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? continueURL)"
            )
        else { return }
        NSWorkspace.shared.open(signInURL)
        googleSessionState = "signing_in"
        googleSessionDetail = "Opened Google sign-in in your default browser. CALCIE Player will not ask for your Google password."
    }

    func openEmbeddedGoogleSignIn(for platform: String = "youtube") {
        ensurePlayerSurface()
        let normalizedPlatform = platform == "ytmusic" ? "ytmusic" : "youtube"
        let continueURL = normalizedPlatform == "ytmusic"
            ? "https://music.youtube.com/"
            : "https://www.youtube.com/"
        guard
            let signInURL = URL(
                string: "https://accounts.google.com/ServiceLogin?service=youtube&continue=\(continueURL.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? continueURL)"
            )
        else { return }

        allowEmbeddedGoogleLogin = true
        currentPlatform = normalizedPlatform
        currentTitle = normalizedPlatform == "ytmusic" ? "YouTube Music Premium Login" : "YouTube Premium Login"
        currentSubtitle = "Opening Google's real login page inside CALCIE Player so YouTube Premium cookies can stay in this player."
        googleSessionState = "signing_in"
        googleSessionDetail = "Premium login is enabled for this player window. Use this only if you trust this CALCIE build."
        playerSurfaceState = "loading"
        playerPanel?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        webView?.load(URLRequest(url: signInURL))
    }

    func signOutGoogleSession() {
        let dataTypes = WKWebsiteDataStore.allWebsiteDataTypes()
        websiteDataStore.fetchDataRecords(ofTypes: dataTypes) { [weak self] records in
            guard let self else { return }
            let targets = records.filter {
                let host = $0.displayName.lowercased()
                return host.contains("google") || host.contains("youtube")
            }
            self.websiteDataStore.removeData(ofTypes: dataTypes, for: targets) {
                DispatchQueue.main.async {
                    self.googleSessionState = "signed_out"
                    self.googleSessionDetail = "Cleared Google and YouTube session data from CALCIE Player."
                    self.currentSubtitle = "Google session cleared. Sign in again if you want account continuity."
                }
            }
        }
    }

    func refreshGoogleSessionStatus() {
        websiteDataStore.httpCookieStore.getAllCookies { [weak self] cookies in
            guard let self else { return }
            let relevantCookies = cookies.filter { cookie in
                let domain = cookie.domain.lowercased()
                return domain.contains("google.com") || domain.contains("youtube.com")
            }
            let sessionCookieNames: Set<String> = ["sid", "apisid", "sapisid", "login_info", "__secure-1psid", "__secure-3psid"]
            let hasSessionCookies = relevantCookies.contains {
                sessionCookieNames.contains($0.name.lowercased())
            }

            DispatchQueue.main.async {
                if self.currentURLString.contains("accounts.google.com") || self.currentURLString.lowercased().contains("servicelogin") {
                    self.googleSessionState = "signing_in"
                    self.googleSessionDetail = "Google sign-in should continue in your browser, not inside CALCIE Player."
                } else if hasSessionCookies {
                    self.googleSessionState = "signed_in"
                    self.googleSessionDetail = "Google session detected for YouTube/YouTube Music in CALCIE Player."
                } else {
                    self.googleSessionState = "signed_out"
                    self.googleSessionDetail = "No Google session detected in CALCIE Player yet."
                }
            }
        }
    }

    func handleCommand(_ command: MediaPlayerCommandRequest) {
        let action = command.action.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        lastCommandAction = action
        switch action {
        case "load":
            guard let rawURL = command.url, let url = URL(string: rawURL) else {
                playerSurfaceState = "error"
                currentSubtitle = "Player command failed: missing or invalid media URL."
                return
            }
            ensurePlayerSurface()
            if command.show_player ?? true {
                playerPanel?.makeKeyAndOrderFront(nil)
                NSApp.activate(ignoringOtherApps: true)
            }
            if let title = command.title, !title.isEmpty {
                currentTitle = title
            } else {
                currentTitle = "CALCIE Player"
            }
            if let subtitle = command.subtitle, !subtitle.isEmpty {
                currentSubtitle = subtitle
            } else {
                currentSubtitle = "Loading media in the CALCIE-owned player surface."
            }
            currentURLString = rawURL
            if let platform = command.platform, !platform.isEmpty {
                currentPlatform = platform
            } else {
                currentPlatform = inferPlatform(from: url)
            }
            if let query = command.query, !query.isEmpty {
                lastResolvedQuery = query
            }
            if isPlayableMediaURL(url) {
                lastPlayableURLString = rawURL
                if let title = command.title, !title.isEmpty {
                    lastPlayableTitle = title
                }
                rememberHistoryItem(
                    url: rawURL,
                    title: command.title ?? currentTitle,
                    platform: currentPlatform,
                    query: command.query ?? lastResolvedQuery
                )
            }
            playerSurfaceState = "loading"
            persistSessionState()
            webView?.load(URLRequest(url: url))
        case "pause":
            pauseCurrentMedia()
        case "mute":
            setMuted(true)
        case "unmute":
            setMuted(false)
        case "volume_up":
            adjustVolume(delta: 0.1)
        case "volume_down":
            adjustVolume(delta: -0.1)
        case "set_volume":
            let volumePercent = Double(command.subtitle ?? "") ?? 50
            setVolume(volumePercent / 100.0)
        case "speed_up":
            adjustPlaybackSpeed(delta: 0.25)
        case "speed_down":
            adjustPlaybackSpeed(delta: -0.25)
        case "set_speed":
            let speed = Double(command.subtitle ?? "") ?? 1.0
            setPlaybackSpeed(speed)
        case "seek_forward":
            let seconds = Double(command.subtitle ?? "") ?? 10
            seekCurrentMedia(by: abs(seconds))
        case "seek_backward":
            let seconds = Double(command.subtitle ?? "") ?? 10
            seekCurrentMedia(by: -abs(seconds))
        case "next":
            skipToNextMedia()
        case "previous":
            goToPreviousMedia()
        case "previous_track":
            goToPreviousTrack()
        case "restart_current":
            restartCurrentMedia()
        case "play", "resume":
            resumeCurrentMedia()
        default:
            currentSubtitle = "Ignored unsupported player action: \(command.action)"
        }
    }

    private func ensurePlayerSurface() {
        if webView == nil {
            let configuration = WKWebViewConfiguration()
            configuration.mediaTypesRequiringUserActionForPlayback = []
            configuration.websiteDataStore = websiteDataStore
            let createdWebView = WKWebView(frame: .zero, configuration: configuration)
            createdWebView.navigationDelegate = self
            createdWebView.allowsMagnification = true
            createdWebView.allowsBackForwardNavigationGestures = true
            createdWebView.customUserAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Safari/605.1.15"
            createdWebView.setValue(false, forKey: "drawsBackground")
            webView = createdWebView
        }

        if playerPanel == nil, let webView {
            let panel = NSPanel(
                contentRect: NSRect(x: 0, y: 0, width: 460, height: 760),
                styleMask: [.titled, .closable, .resizable, .fullSizeContentView],
                backing: .buffered,
                defer: false
            )
            panel.isFloatingPanel = false
            panel.level = .normal
            panel.hidesOnDeactivate = false
            panel.title = "CALCIE Player"
            panel.titlebarAppearsTransparent = true
            panel.isReleasedWhenClosed = false
            panel.center()
            panel.contentViewController = NSHostingController(
                rootView: PlayerSurfaceView(manager: self, webView: webView)
            )
            playerPanel = panel
        }
    }

    func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
        playerSurfaceState = "loading"
    }

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping @MainActor @Sendable (WKNavigationActionPolicy) -> Void
    ) {
        guard let url = navigationAction.request.url else {
            decisionHandler(.allow)
            return
        }

        if shouldOpenGoogleAuthExternally(url) {
            NSWorkspace.shared.open(url)
            googleSessionState = "signing_in"
            googleSessionDetail = "Google sign-in opened in your browser. CALCIE does not collect your Google password."
            currentSubtitle = "Google login was moved to your browser for safety."
            decisionHandler(.cancel)
            return
        }

        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        playerSurfaceState = "ready"
        if let title = webView.title, !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            currentTitle = title
        }
        if let url = webView.url {
            currentURLString = url.absoluteString
            currentPlatform = inferPlatform(from: url)
            if isPlayableMediaURL(url) {
                lastPlayableURLString = url.absoluteString
                lastPlayableTitle = currentTitle
                rememberHistoryItem(
                    url: url.absoluteString,
                    title: currentTitle,
                    platform: currentPlatform,
                    query: lastResolvedQuery
                )
            }
        }
        currentSubtitle = "Single CALCIE-owned player surface. Future play commands should reuse this window."
        persistSessionState()
        refreshGoogleSessionStatus()
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        playerSurfaceState = "error"
        currentSubtitle = "Player load failed: \(error.localizedDescription)"
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        playerSurfaceState = "error"
        currentSubtitle = "Player load failed: \(error.localizedDescription)"
    }

    private func shouldOpenGoogleAuthExternally(_ url: URL) -> Bool {
        if allowEmbeddedGoogleLogin {
            return false
        }

        let host = (url.host ?? "").lowercased()
        let path = url.path.lowercased()
        let fullURL = url.absoluteString.lowercased()

        if host.contains("accounts.google.com") {
            return true
        }
        if host.contains("google.com"), path.contains("signin") || path.contains("servicelogin") {
            return true
        }
        if fullURL.contains("accounts.google.com") || fullURL.contains("servicelogin") {
            return true
        }

        return false
    }

    private func pauseCurrentMedia() {
        ensurePlayerSurface()
        runPlaybackScript(
            """
            (() => {
              const video = document.querySelector('video');
              if (video) {
                video.pause();
                return 'paused-video';
              }
              const button = [...document.querySelectorAll('button')].find((candidate) => {
                const label = (candidate.getAttribute('aria-label') || '').toLowerCase();
                return label.includes('pause');
              });
              if (button) {
                button.click();
                return 'clicked-pause';
              }
              return 'no-pause-target';
            })();
            """,
            successSubtitle: "Pause command sent to CALCIE Player.",
            emptySubtitle: "CALCIE Player did not find a pause target on the current page."
        )
    }

    private func setMuted(_ muted: Bool) {
        ensurePlayerSurface()
        let mutedValue = muted ? "true" : "false"
        runPlaybackScript(
            """
            (() => {
              const video = document.querySelector('video');
              if (video) {
                video.muted = \(mutedValue);
                return video.muted ? 'muted' : 'unmuted';
              }
              return 'no-video';
            })();
            """,
            successSubtitle: muted ? "CALCIE Player muted." : "CALCIE Player unmuted.",
            emptySubtitle: "CALCIE Player did not find an audio target on the current page."
        )
    }

    private func adjustVolume(delta: Double) {
        ensurePlayerSurface()
        runPlaybackScript(
            """
            (() => {
              const video = document.querySelector('video');
              if (video) {
                const nextVolume = Math.max(0, Math.min(1, (video.volume ?? 1) + \(delta)));
                video.volume = nextVolume;
                video.muted = false;
                return `volume:${nextVolume.toFixed(2)}`;
              }
              return 'no-video';
            })();
            """,
            successSubtitle: delta >= 0 ? "CALCIE Player volume increased." : "CALCIE Player volume decreased.",
            emptySubtitle: "CALCIE Player did not find a volume target on the current page."
        )
    }

    private func setVolume(_ value: Double) {
        ensurePlayerSurface()
        let clamped = max(0.0, min(1.0, value))
        runPlaybackScript(
            """
            (() => {
              const video = document.querySelector('video');
              if (video) {
                video.volume = \(clamped);
                video.muted = false;
                return `volume:${video.volume.toFixed(2)}`;
              }
              return 'no-video';
            })();
            """,
            successSubtitle: "CALCIE Player volume updated.",
            emptySubtitle: "CALCIE Player did not find a volume target on the current page."
        )
    }

    private func adjustPlaybackSpeed(delta: Double) {
        ensurePlayerSurface()
        runPlaybackScript(
            """
            (() => {
              const video = document.querySelector('video');
              if (video) {
                const nextRate = Math.max(0.25, Math.min(3, (video.playbackRate || 1) + \(delta)));
                video.playbackRate = nextRate;
                return `speed:${nextRate.toFixed(2)}`;
              }
              return 'no-video';
            })();
            """,
            successSubtitle: delta >= 0 ? "CALCIE Player speed increased." : "CALCIE Player speed decreased.",
            emptySubtitle: "CALCIE Player did not find a playback-speed target on the current page."
        )
    }

    private func setPlaybackSpeed(_ value: Double) {
        ensurePlayerSurface()
        let clamped = max(0.25, min(3.0, value))
        runPlaybackScript(
            """
            (() => {
              const video = document.querySelector('video');
              if (video) {
                video.playbackRate = \(clamped);
                return `speed:${video.playbackRate.toFixed(2)}`;
              }
              return 'no-video';
            })();
            """,
            successSubtitle: "CALCIE Player playback speed updated.",
            emptySubtitle: "CALCIE Player did not find a playback-speed target on the current page."
        )
    }

    private func seekCurrentMedia(by seconds: Double) {
        ensurePlayerSurface()
        runPlaybackScript(
            """
            (() => {
              const video = document.querySelector('video');
              if (video) {
                const duration = Number.isFinite(video.duration) ? video.duration : Number.MAX_SAFE_INTEGER;
                const nextTime = Math.max(0, Math.min(duration, (video.currentTime || 0) + \(seconds)));
                video.currentTime = nextTime;
                return `time:${Math.round(nextTime)}`;
              }
              return 'no-video';
            })();
            """,
            successSubtitle: seconds >= 0 ? "CALCIE Player seeked forward." : "CALCIE Player seeked backward.",
            emptySubtitle: "CALCIE Player did not find a seek target on the current page."
        )
    }

    private func resumeCurrentMedia() {
        ensurePlayerSurface()
        runPlaybackScript(
            """
            (() => {
              const video = document.querySelector('video');
              if (video) {
                video.muted = false;
                video.play();
                return 'playing-video';
              }
              const button = [...document.querySelectorAll('button')].find((candidate) => {
                const label = (candidate.getAttribute('aria-label') || '').toLowerCase();
                const title = (candidate.getAttribute('title') || '').toLowerCase();
                return label.includes('play') || label.includes('resume') || title.includes('play') || title.includes('resume');
              });
              if (button) {
                button.click();
                return 'clicked-play';
              }
              return 'no-play-target';
            })();
            """,
            successSubtitle: "Play command sent to CALCIE Player.",
            emptySubtitle: "CALCIE Player did not find a play target on the current page.",
            onResult: { [weak self] result in
                guard let self else { return }
                if result == "no-play-target" {
                    _ = self.loadLastPlayableMediaIfAvailable(autoplayHint: true)
                }
            }
        )
    }

    private func skipToNextMedia() {
        ensurePlayerSurface()
        if navigateHistory(offset: 1, subtitle: "Opening the next remembered media item in CALCIE Player.") {
            return
        }
        runPlaybackScript(
            """
            (() => {
              const byLabel = (terms) => [...document.querySelectorAll('button,a')].find((candidate) => {
                const label = (candidate.getAttribute('aria-label') || '').toLowerCase();
                const title = (candidate.getAttribute('title') || '').toLowerCase();
                const text = (candidate.textContent || '').toLowerCase();
                return terms.some((term) => label.includes(term) || title.includes(term) || text.includes(term));
              });

              const nextButton = byLabel(['next', 'skip']);
              if (nextButton) {
                nextButton.click();
                return 'clicked-next';
              }

              const video = document.querySelector('video');
              if (video) {
                const event = new KeyboardEvent('keydown', { key: 'N', shiftKey: true, bubbles: true });
                document.dispatchEvent(event);
                return 'dispatched-shift-n';
              }

              return 'no-next-target';
            })();
            """,
            successSubtitle: "Next command sent to CALCIE Player.",
            emptySubtitle: "CALCIE Player did not find a next target on the current page."
        )
    }

    private func goToPreviousMedia() {
        ensurePlayerSurface()
        runPlaybackScript(
            """
            (() => {
              const byLabel = (terms) => [...document.querySelectorAll('button,a')].find((candidate) => {
                const label = (candidate.getAttribute('aria-label') || '').toLowerCase();
                const title = (candidate.getAttribute('title') || '').toLowerCase();
                const text = (candidate.textContent || '').toLowerCase();
                return terms.some((term) => label.includes(term) || title.includes(term) || text.includes(term));
              });

              const previousButton = byLabel(['previous', 'prev', 'back']);
              if (previousButton) {
                previousButton.click();
                return 'clicked-previous';
              }

              if (window.history.length > 1) {
                window.history.back();
                return 'history-back';
              }

              const video = document.querySelector('video');
              if (video) {
                const event = new KeyboardEvent('keydown', { key: 'P', shiftKey: true, bubbles: true });
                document.dispatchEvent(event);
                return 'dispatched-shift-p';
              }

              return 'no-previous-target';
            })();
            """,
            successSubtitle: "Previous command sent to CALCIE Player.",
            emptySubtitle: "CALCIE Player did not find a previous target on the current page."
        )
    }

    private func goToPreviousTrack() {
        ensurePlayerSurface()
        if navigateHistory(offset: -1, subtitle: "Opening the previous remembered track in CALCIE Player.") {
            return
        }
        runPlaybackScript(
            """
            (() => {
              const byLabel = (terms) => [...document.querySelectorAll('button,a')].find((candidate) => {
                const label = (candidate.getAttribute('aria-label') || '').toLowerCase();
                const title = (candidate.getAttribute('title') || '').toLowerCase();
                const text = (candidate.textContent || '').toLowerCase();
                return terms.some((term) => label.includes(term) || title.includes(term) || text.includes(term));
              });

              const previousButton = byLabel(['previous', 'prev', 'back']);
              if (previousButton) {
                previousButton.click();
                setTimeout(() => previousButton.click(), 140);
                return 'double-clicked-previous';
              }

              const video = document.querySelector('video');
              if (video) {
                const dispatchPrevious = () => {
                  const event = new KeyboardEvent('keydown', { key: 'P', shiftKey: true, bubbles: true });
                  document.dispatchEvent(event);
                };
                dispatchPrevious();
                setTimeout(dispatchPrevious, 140);
                return 'double-dispatched-shift-p';
              }

              return 'no-previous-track-target';
            })();
            """,
            successSubtitle: "Previous-track command sent to CALCIE Player.",
            emptySubtitle: "CALCIE Player did not find a previous-track target on the current page."
        )
    }

    private func restartCurrentMedia() {
        ensurePlayerSurface()
        runPlaybackScript(
            """
            (() => {
              const byLabel = (terms) => [...document.querySelectorAll('button,a')].find((candidate) => {
                const label = (candidate.getAttribute('aria-label') || '').toLowerCase();
                const title = (candidate.getAttribute('title') || '').toLowerCase();
                const text = (candidate.textContent || '').toLowerCase();
                return terms.some((term) => label.includes(term) || title.includes(term) || text.includes(term));
              });

              const previousButton = byLabel(['previous', 'prev', 'back']);
              if (previousButton) {
                previousButton.click();
                return 'clicked-previous-once';
              }

              const video = document.querySelector('video');
              if (video) {
                video.currentTime = 0;
                if (video.paused) {
                  video.play();
                }
                return 'restarted-video';
              }

              return 'no-restart-target';
            })();
            """,
            successSubtitle: "Restart command sent to CALCIE Player.",
            emptySubtitle: "CALCIE Player did not find a restart target on the current page."
        )
    }

    @discardableResult
    private func loadLastPlayableMediaIfAvailable(autoplayHint: Bool = false) -> Bool {
        guard let url = preferredResumeURL() else { return false }
        if autoplayHint {
            currentSubtitle = "Reopening the last known playable media page in CALCIE Player."
        } else {
            currentSubtitle = "Reusing the last known playable media page in CALCIE Player."
        }
        currentURLString = url.absoluteString
        if !lastPlayableTitle.isEmpty {
            currentTitle = lastPlayableTitle
        }
        playerSurfaceState = "loading"
        webView?.load(URLRequest(url: url))
        return true
    }

    @discardableResult
    private func navigateHistory(offset: Int, subtitle: String) -> Bool {
        guard let currentIndex = currentHistoryIndex else { return false }
        let nextIndex = currentIndex + offset
        guard recentHistory.indices.contains(nextIndex) else { return false }
        let item = recentHistory[nextIndex]
        guard let url = URL(string: item.url) else { return false }
        currentHistoryIndex = nextIndex
        currentURLString = item.url
        currentTitle = item.title
        currentPlatform = item.platform
        lastResolvedQuery = item.query
        currentSubtitle = subtitle
        playerSurfaceState = "loading"
        webView?.load(URLRequest(url: url))
        return true
    }

    private func rememberHistoryItem(url: String, title: String, platform: String, query: String) {
        let normalizedTitle = title.trimmingCharacters(in: .whitespacesAndNewlines)
        let normalizedPlatform = platform.isEmpty ? "unknown" : platform
        let item = MediaHistoryItem(
            url: url,
            title: normalizedTitle.isEmpty ? "Untitled media" : normalizedTitle,
            platform: normalizedPlatform,
            query: query
        )

        if let existingIndex = recentHistory.firstIndex(where: { $0.url == url }) {
            recentHistory[existingIndex] = item
            currentHistoryIndex = existingIndex
            persistSessionState()
            return
        }

        if let currentIndex = currentHistoryIndex, currentIndex < recentHistory.count - 1 {
            recentHistory = Array(recentHistory.prefix(currentIndex + 1))
        }

        recentHistory.append(item)
        if recentHistory.count > 12 {
            recentHistory.removeFirst(recentHistory.count - 12)
        }
        currentHistoryIndex = recentHistory.indices.last
        persistSessionState()
    }

    private func loadPersistedSessionState() {
        guard let data = try? Data(contentsOf: sessionStateURL) else { return }
        guard let state = try? JSONDecoder().decode(PersistedMediaSessionState.self, from: data) else { return }
        currentURLString = state.currentURLString
        lastPlayableURLString = state.lastPlayableURLString
        lastPlayableTitle = state.lastPlayableTitle
        currentPlatform = state.currentPlatform
        lastResolvedQuery = state.lastResolvedQuery
        lastCommandAction = state.lastCommandAction
        recentHistory = state.recentHistory.map {
            MediaHistoryItem(url: $0.url, title: $0.title, platform: $0.platform, query: $0.query)
        }
        currentHistoryIndex = state.currentHistoryIndex
    }

    private func persistSessionState() {
        do {
            try FileManager.default.createDirectory(
                at: sessionStateURL.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            let state = PersistedMediaSessionState(
                currentURLString: currentURLString,
                lastPlayableURLString: lastPlayableURLString,
                lastPlayableTitle: lastPlayableTitle,
                currentPlatform: currentPlatform,
                lastResolvedQuery: lastResolvedQuery,
                lastCommandAction: lastCommandAction,
                recentHistory: recentHistory.map {
                    PersistedMediaHistoryItem(url: $0.url, title: $0.title, platform: $0.platform, query: $0.query)
                },
                currentHistoryIndex: currentHistoryIndex
            )
            let data = try JSONEncoder().encode(state)
            try data.write(to: sessionStateURL, options: .atomic)
        } catch {
            currentSubtitle = "Player state persistence failed: \(error.localizedDescription)"
        }
    }

    private func preferredResumeURL() -> URL? {
        if let current = URL(string: currentURLString), isPlayableMediaURL(current) {
            return current
        }
        if let lastPlayable = URL(string: lastPlayableURLString), isPlayableMediaURL(lastPlayable) {
            return lastPlayable
        }
        return nil
    }

    private func isPlayableMediaURL(_ url: URL) -> Bool {
        let host = (url.host ?? "").lowercased()
        let path = url.path.lowercased()
        guard host.contains("youtube.com") else { return false }
        if host.contains("music.youtube.com") || host.contains("www.youtube.com") || host == "youtube.com" {
            return path == "/watch"
        }
        return false
    }

    private func inferPlatform(from url: URL) -> String {
        let host = (url.host ?? "").lowercased()
        if host.contains("music.youtube.com") {
            return "ytmusic"
        }
        if host.contains("youtube.com") {
            return "youtube"
        }
        return "unknown"
    }

    private func runPlaybackScript(
        _ script: String,
        successSubtitle: String,
        emptySubtitle: String,
        onResult: ((String) -> Void)? = nil
    ) {
        webView?.evaluateJavaScript(script) { [weak self] result, error in
            Task { @MainActor in
                guard let self else { return }
                if let error {
                    self.playerSurfaceState = "error"
                    self.currentSubtitle = "Player control failed: \(error.localizedDescription)"
                    return
                }
                let resultString = result as? String
                if result == nil {
                    self.currentSubtitle = emptySubtitle
                } else {
                    self.currentSubtitle = successSubtitle
                }
                if let resultString {
                    onResult?(resultString)
                }
            }
        }
    }
}

private struct PlayerSurfaceView: View {
    @ObservedObject var manager: MediaSessionManager
    let webView: WKWebView
    @State private var showControls = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            playerHeader

            PlayerWebViewContainer(webView: webView)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            DisclosureGroup(isExpanded: $showControls) {
                controlsPanel
                    .padding(.top, 8)
            } label: {
                Text("Controls & Account")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .frame(minWidth: 430, minHeight: 720)
    }

    private var playerHeader: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(manager.currentTitle)
                    .font(.headline)
                    .lineLimit(1)
                Spacer()
                Text(manager.playerSurfaceState.capitalized)
                    .font(.caption.weight(.semibold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(.thinMaterial, in: Capsule())
            }
            Text(manager.currentSubtitle)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
            if manager.googleSessionState == "signing_in" {
                Text("Google login continues in your browser. CALCIE Player will not ask for your Google password.")
                    .font(.caption2)
                    .foregroundStyle(.orange)
                    .lineLimit(2)
            }
        }
    }

    private var controlsPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            if manager.currentPlatform != "unknown" || !manager.lastResolvedQuery.isEmpty {
                Text("Platform: \(manager.currentPlatform) · Query: \(manager.lastResolvedQuery.isEmpty ? "-" : manager.lastResolvedQuery)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            if !manager.lastPlayableTitle.isEmpty {
                Text("Last playable: \(manager.lastPlayableTitle)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Text("Google session: \(manager.googleSessionState)")
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(manager.googleSessionDetail)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Text(manager.googleSessionFallbackHint)
                .font(.caption2)
                .foregroundStyle(.orange)
                .fixedSize(horizontal: false, vertical: true)
            if !manager.currentURLString.isEmpty {
                Text(manager.currentURLString)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            HStack {
                Button("Reload") {
                    manager.reloadCurrentMedia()
                }
                Button("Bootstrap Video") {
                    manager.loadBootstrapMedia()
                }
                Button("Previous") {
                    manager.handleCommand(
                        MediaPlayerCommandRequest(
                            action: "previous_track",
                            request_id: nil,
                            requested_at: nil,
                            url: nil,
                            title: nil,
                            subtitle: nil,
                            platform: nil,
                            query: nil,
                            show_player: false
                        )
                    )
                }
                Button("Restart") {
                    manager.handleCommand(
                        MediaPlayerCommandRequest(
                            action: "restart_current",
                            request_id: nil,
                            requested_at: nil,
                            url: nil,
                            title: nil,
                            subtitle: nil,
                            platform: nil,
                            query: nil,
                            show_player: false
                        )
                    )
                }
                Button("Next") {
                    manager.handleCommand(
                        MediaPlayerCommandRequest(
                            action: "next",
                            request_id: nil,
                            requested_at: nil,
                            url: nil,
                            title: nil,
                            subtitle: nil,
                            platform: nil,
                            query: nil,
                            show_player: false
                        )
                    )
                }
            }
            .buttonStyle(.bordered)

            HStack {
                Button("Premium Login") {
                    manager.openEmbeddedGoogleSignIn(for: manager.currentPlatform == "ytmusic" ? "ytmusic" : "youtube")
                }
                Button("Browser YT Login") {
                    manager.openGoogleSignIn(for: "youtube")
                }
                Button("Browser Music Login") {
                    manager.openGoogleSignIn(for: "ytmusic")
                }
                Button("Sign Out") {
                    manager.signOutGoogleSession()
                }
                Button("Google Login") {
                    manager.openGoogleSignInInBrowser(for: "youtube")
                }
            }
            .buttonStyle(.bordered)

            HStack {
                Button("YouTube Home") {
                    manager.openProviderHome("youtube")
                }
                Button("Music Home") {
                    manager.openProviderHome("ytmusic")
                }
            }
            .buttonStyle(.bordered)

            HStack {
                Button("Mute") {
                    manager.handleCommand(
                        MediaPlayerCommandRequest(
                            action: "mute",
                            request_id: nil,
                            requested_at: nil,
                            url: nil,
                            title: nil,
                            subtitle: nil,
                            platform: nil,
                            query: nil,
                            show_player: false
                        )
                    )
                }
                Button("Vol -") {
                    manager.handleCommand(
                        MediaPlayerCommandRequest(
                            action: "volume_down",
                            request_id: nil,
                            requested_at: nil,
                            url: nil,
                            title: nil,
                            subtitle: nil,
                            platform: nil,
                            query: nil,
                            show_player: false
                        )
                    )
                }
                Button("Vol +") {
                    manager.handleCommand(
                        MediaPlayerCommandRequest(
                            action: "volume_up",
                            request_id: nil,
                            requested_at: nil,
                            url: nil,
                            title: nil,
                            subtitle: nil,
                            platform: nil,
                            query: nil,
                            show_player: false
                        )
                    )
                }
                Button("-10s") {
                    manager.handleCommand(
                        MediaPlayerCommandRequest(
                            action: "seek_backward",
                            request_id: nil,
                            requested_at: nil,
                            url: nil,
                            title: nil,
                            subtitle: "10",
                            platform: nil,
                            query: nil,
                            show_player: false
                        )
                    )
                }
                Button("+10s") {
                    manager.handleCommand(
                        MediaPlayerCommandRequest(
                            action: "seek_forward",
                            request_id: nil,
                            requested_at: nil,
                            url: nil,
                            title: nil,
                            subtitle: "10",
                            platform: nil,
                            query: nil,
                            show_player: false
                        )
                    )
                }
            }
            .buttonStyle(.bordered)

            HStack {
                Button("Slower") {
                    manager.handleCommand(
                        MediaPlayerCommandRequest(
                            action: "speed_down",
                            request_id: nil,
                            requested_at: nil,
                            url: nil,
                            title: nil,
                            subtitle: nil,
                            platform: nil,
                            query: nil,
                            show_player: false
                        )
                    )
                }
                Button("Faster") {
                    manager.handleCommand(
                        MediaPlayerCommandRequest(
                            action: "speed_up",
                            request_id: nil,
                            requested_at: nil,
                            url: nil,
                            title: nil,
                            subtitle: nil,
                            platform: nil,
                            query: nil,
                            show_player: false
                        )
                    )
                }
            }
            .buttonStyle(.bordered)

            if !manager.recentHistory.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Recent")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    ForEach(Array(manager.recentHistory.enumerated().suffix(3)), id: \.element.id) { index, item in
                        Text("\(manager.currentHistoryIndex == index ? "•" : "·") \(item.title)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
            }
        }
    }
}

private struct PlayerWebViewContainer: NSViewRepresentable {
    let webView: WKWebView

    func makeNSView(context: Context) -> WKWebView {
        webView
    }

    func updateNSView(_ nsView: WKWebView, context: Context) {
    }
}
