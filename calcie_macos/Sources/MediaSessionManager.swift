import AppKit
import SwiftUI
import WebKit

struct MediaPlayerCommandRequest: Decodable {
    let action: String
    let request_id: String?
    let requested_at: String?
    let url: String?
    let title: String?
    let subtitle: String?
    let show_player: Bool?
}

@MainActor
final class MediaSessionManager: NSObject, ObservableObject, WKNavigationDelegate {
    @Published var playerSurfaceState = "idle"
    @Published var currentTitle = "No media loaded"
    @Published var currentSubtitle = "Phase 1 player surface is ready."
    @Published var currentURLString = ""

    private(set) var playerPanel: NSPanel?
    private(set) var webView: WKWebView?
    private let bootstrapURL = URL(string: "https://www.youtube.com/watch?v=jNQXAC9IVRw")!

    func showPlayer() {
        ensurePlayerSurface()
        if currentURLString.isEmpty {
            loadBootstrapMedia()
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
        loadBootstrapMedia()
    }

    func handleCommand(_ command: MediaPlayerCommandRequest) {
        let action = command.action.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
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
            playerSurfaceState = "loading"
            webView?.load(URLRequest(url: url))
        case "pause":
            pauseCurrentMedia()
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

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        playerSurfaceState = "ready"
        if let title = webView.title, !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            currentTitle = title
        }
        currentURLString = webView.url?.absoluteString ?? currentURLString
        currentSubtitle = "Single CALCIE-owned player surface. Future play commands should reuse this window."
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        playerSurfaceState = "error"
        currentSubtitle = "Player load failed: \(error.localizedDescription)"
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        playerSurfaceState = "error"
        currentSubtitle = "Player load failed: \(error.localizedDescription)"
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

    private func resumeCurrentMedia() {
        ensurePlayerSurface()
        runPlaybackScript(
            """
            (() => {
              const video = document.querySelector('video');
              if (video) {
                const playPromise = video.play();
                return playPromise ? 'playing-video' : 'playing-video';
              }
              const button = [...document.querySelectorAll('button')].find((candidate) => {
                const label = (candidate.getAttribute('aria-label') || '').toLowerCase();
                return label.includes('play') || label.includes('resume');
              });
              if (button) {
                button.click();
                return 'clicked-play';
              }
              return 'no-play-target';
            })();
            """,
            successSubtitle: "Play command sent to CALCIE Player.",
            emptySubtitle: "CALCIE Player did not find a play target on the current page."
        )
    }

    private func runPlaybackScript(_ script: String, successSubtitle: String, emptySubtitle: String) {
        webView?.evaluateJavaScript(script) { [weak self] result, error in
            Task { @MainActor in
                guard let self else { return }
                if let error {
                    self.playerSurfaceState = "error"
                    self.currentSubtitle = "Player control failed: \(error.localizedDescription)"
                    return
                }
                if result == nil {
                    self.currentSubtitle = emptySubtitle
                } else {
                    self.currentSubtitle = successSubtitle
                }
            }
        }
    }
}

private struct PlayerSurfaceView: View {
    @ObservedObject var manager: MediaSessionManager
    let webView: WKWebView

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text(manager.currentTitle)
                        .font(.headline)
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
                    .fixedSize(horizontal: false, vertical: true)
                if !manager.currentURLString.isEmpty {
                    Text(manager.currentURLString)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }

            HStack {
                Button("Reload") {
                    manager.reloadCurrentMedia()
                }
                Button("Bootstrap Video") {
                    manager.loadBootstrapMedia()
                }
            }
            .buttonStyle(.bordered)

            Divider()

            PlayerWebViewContainer(webView: webView)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
        .padding(16)
        .frame(minWidth: 430, minHeight: 720)
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
