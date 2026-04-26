import AppKit
import Combine
import SwiftUI

private struct WindowFrameObserver: NSViewRepresentable {
    let onWindowChange: (NSWindow?) -> Void

    func makeNSView(context: Context) -> NSView {
        let view = TrackingView()
        view.onWindowChange = onWindowChange
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        guard let view = nsView as? TrackingView else { return }
        view.onWindowChange = onWindowChange
        DispatchQueue.main.async {
            view.reportWindow()
        }
    }

    final class TrackingView: NSView {
        var onWindowChange: ((NSWindow?) -> Void)?

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            reportWindow()
        }

        override func viewDidChangeBackingProperties() {
            super.viewDidChangeBackingProperties()
            reportWindow()
        }

        func reportWindow() {
            onWindowChange?(window)
        }
    }
}

@main
struct CalcieMenuBarApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        Settings {
            EmptyView()
        }
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private let viewModel = ShellViewModel()
    private let mediaSessionManager = MediaSessionManager()
    private var statusBarController: StatusBarController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        if let appIcon = StatusBarController.calcieLogoImage(pointSize: 256, template: false) {
            NSApp.applicationIconImage = appIcon
        }
        statusBarController = StatusBarController(viewModel: viewModel, mediaSessionManager: mediaSessionManager)
        viewModel.dismissPanelHandler = { [weak self] in
            self?.statusBarController?.closePopover()
        }
        viewModel.openAdvancedOptionsHandler = { [weak self] in
            self?.statusBarController?.showAdvancedOptions()
        }
        viewModel.mediaPlayerCommandHandler = { [weak self] command in
            self?.mediaSessionManager.handleCommand(command)
        }
        HotkeyManager.shared.onHoldStart = { [weak self] in
            self?.viewModel.startVoiceSession()
        }
        HotkeyManager.shared.onHoldEnd = { [weak self] in
            self?.viewModel.stopVoiceSession()
        }
        HotkeyManager.shared.registerDefaultHotkey()
        viewModel.start()
    }

    func applicationWillTerminate(_ notification: Notification) {
        viewModel.clearPanelFrame()
        viewModel.stop()
    }
}

@MainActor
final class StatusBarController: NSObject, NSPopoverDelegate {
    private let statusItem: NSStatusItem
    private let popover: NSPopover
    private let viewModel: ShellViewModel
    private let mediaSessionManager: MediaSessionManager
    private var advancedPanel: NSPanel?
    private var cancellables: Set<AnyCancellable> = []

    init(viewModel: ShellViewModel, mediaSessionManager: MediaSessionManager) {
        self.viewModel = viewModel
        self.mediaSessionManager = mediaSessionManager
        self.statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        self.popover = NSPopover()
        super.init()

        let rootView = MenuBarContentView(viewModel: viewModel, mediaSessionManager: mediaSessionManager)
            .frame(width: 520)

        popover.behavior = .transient
        popover.animates = false
        popover.delegate = self
        popover.contentSize = NSSize(width: 540, height: 680)
        popover.contentViewController = NSHostingController(rootView: rootView)

        if let button = statusItem.button {
            button.target = self
            button.action = #selector(togglePopover(_:))
            button.sendAction(on: [.leftMouseUp, .rightMouseUp])
            button.imagePosition = .imageOnly
            button.image = statusItemImage(for: viewModel.runtimeState)
            button.toolTip = "CALCIE"
        }

        viewModel.$runtimeState
            .receive(on: RunLoop.main)
            .sink { [weak self] state in
                self?.statusItem.button?.image = self?.statusItemImage(for: state)
            }
            .store(in: &cancellables)
    }

    @objc
    private func togglePopover(_ sender: AnyObject?) {
        if popover.isShown {
            closePopover()
        } else {
            showPopover()
        }
    }

    func closePopover() {
        guard popover.isShown else {
            viewModel.clearPanelFrame()
            return
        }
        popover.performClose(nil)
        viewModel.clearPanelFrame()
    }

    func showAdvancedOptions() {
        if advancedPanel == nil {
            let panel = NSPanel(
                contentRect: NSRect(x: 0, y: 0, width: 430, height: 620),
                styleMask: [.titled, .closable, .fullSizeContentView],
                backing: .buffered,
                defer: false
            )
            panel.isFloatingPanel = true
            panel.level = .floating
            panel.hidesOnDeactivate = false
            panel.title = "CALCIE Settings"
            panel.titlebarAppearsTransparent = true
            panel.isReleasedWhenClosed = false
            panel.center()
            panel.contentViewController = NSHostingController(
                rootView: AdvancedOptionsView(viewModel: viewModel, mediaSessionManager: mediaSessionManager)
            )
            advancedPanel = panel
        }
        advancedPanel?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func showPopover() {
        guard let button = statusItem.button else { return }
        popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
        NSApp.activate(ignoringOtherApps: true)
        DispatchQueue.main.async { [weak self] in
            self?.viewModel.updatePanelFrame(self?.popover.contentViewController?.view.window)
        }
    }

    func popoverWillClose(_ notification: Notification) {
        viewModel.clearPanelFrame()
    }

    private func statusItemImage(for state: String) -> NSImage? {
        if let logo = Self.calcieLogoImage(pointSize: 18, template: true) {
            return logo
        }

        let image = NSImage(systemSymbolName: "sparkles", accessibilityDescription: "CALCIE")
        image?.isTemplate = true
        return image
    }

    static func calcieLogoImage(pointSize: CGFloat, template: Bool) -> NSImage? {
        guard let url = Bundle.main.url(forResource: "calcie-logo", withExtension: "png"),
              let image = NSImage(contentsOf: url) else {
            return nil
        }
        image.size = NSSize(width: pointSize, height: pointSize)
        image.isTemplate = template
        return image
    }
}

struct MenuBarContentView: View {
    @ObservedObject var viewModel: ShellViewModel
    @ObservedObject var mediaSessionManager: MediaSessionManager
    @State private var showTools = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            chatHeader
            Divider()
            chatTranscript
            chatComposer
            if !viewModel.commandError.isEmpty {
                Text(viewModel.commandError)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .lineLimit(3)
            }
            Divider()
            DisclosureGroup(isExpanded: $showTools) {
                compactTools
                    .padding(.top, 8)
            } label: {
                Text("Tools & Status")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
            footer
        }
        .padding(14)
        .background(
            WindowFrameObserver { window in
                viewModel.updatePanelFrame(window)
            }
        )
        .onDisappear {
            viewModel.clearPanelFrame()
        }
    }

    private var chatHeader: some View {
        HStack(alignment: .top, spacing: 10) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Ask CALCIE")
                    .font(.headline)
                Text(viewModel.runtimeOnline ? "Follow up, review responses, send normal commands, or use the eye button for a one-time vision check." : "Runtime needs attention before chat can respond.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 4) {
                Text(viewModel.runtimeState.replacingOccurrences(of: "_", with: " "))
                    .font(.caption.weight(.semibold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(.thinMaterial, in: Capsule())
                Button("Clear") {
                    viewModel.clearChat()
                }
                .font(.caption)
            }
        }
    }

    private var chatTranscript: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    ForEach(viewModel.chatMessages) { message in
                        ChatBubble(message: message)
                            .id(message.id)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.vertical, 4)
            }
            .frame(minHeight: 380, maxHeight: 430)
            .onChange(of: viewModel.chatMessages.count) { _ in
                guard let last = viewModel.chatMessages.last else { return }
                DispatchQueue.main.async {
                    withAnimation(.easeOut(duration: 0.18)) {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    }
                }
            }
        }
    }

    private var chatComposer: some View {
        HStack(spacing: 8) {
            Button {
                viewModel.toggleVoice()
            } label: {
                Image(systemName: viewModel.voiceSessionActive ? "mic.fill" : "mic")
            }
            .help(viewModel.voiceSessionActive ? "Stop talking" : "Talk to CALCIE")

            TextField("Ask follow up or describe a vision check...", text: $viewModel.chatInput)
                .onSubmit {
                    viewModel.submitChatMessage()
                }
                .textFieldStyle(.roundedBorder)
                .disabled(viewModel.isSubmittingCommand)

            Button {
                viewModel.submitChatMessage(asVision: true)
            } label: {
                Image(systemName: "eye")
                    .font(.caption.weight(.bold))
            }
            .help("Run this input as a one-time vision check")
            .disabled(viewModel.isSubmittingCommand || viewModel.chatInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

            Button {
                viewModel.submitChatMessage()
            } label: {
                Image(systemName: "arrow.up")
                    .font(.caption.weight(.bold))
            }
            .disabled(viewModel.isSubmittingCommand || viewModel.chatInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            .keyboardShortcut(.return, modifiers: [])
        }
    }

    private var compactTools: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Button(viewModel.voiceSessionActive ? "Stop Talking" : "Talk") {
                    viewModel.toggleVoice()
                }
                Button("Settings") {
                    viewModel.openAdvancedOptions()
                }
                Button("Player") {
                    mediaSessionManager.showPlayer()
                }
                Button("Refresh") {
                    Task { await viewModel.refreshAll() }
                }
            }
            HStack {
                Button("Start Vision") {
                    viewModel.startVision()
                }
                Button("Stop Vision") {
                    viewModel.stopVision()
                }
                Button("Quit") {
                    NSApplication.shared.terminate(nil)
                }
            }
            Text("LLM: \(viewModel.activeLLM) · TTS: \(viewModel.ttsProvider) · Route: \(viewModel.lastRoute)")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(2)
            if !viewModel.runtimeDetail.isEmpty {
                Text(viewModel.runtimeDetail)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("CALCIE")
                    .font(.headline)
                Spacer()
                Text(viewModel.runtimeState.replacingOccurrences(of: "_", with: " "))
                    .font(.caption.weight(.semibold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(.thinMaterial, in: Capsule())
            }
            if !viewModel.runtimeDetail.isEmpty {
                Text(viewModel.runtimeDetail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text(viewModel.runtimeOnline ? "Ready for quick commands" : "Runtime needs attention")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    private var quickActions: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Quick Actions")
                .font(.subheadline.weight(.semibold))
            HStack {
                Button(viewModel.voiceSessionActive ? "Stop Talking" : "Talk to CALCIE") {
                    viewModel.toggleVoice()
                }
                Button("Refresh") {
                    Task { await viewModel.refreshAll() }
                }
            }
            HStack {
                Button("Settings") {
                    viewModel.openAdvancedOptions()
                }
                Button("Open Player") {
                    mediaSessionManager.showPlayer()
                }
            }
            HStack {
                Button("Quit CALCIE") {
                    NSApplication.shared.terminate(nil)
                }
            }
        }
    }

    private var typedCommand: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Type a Command")
                .font(.subheadline.weight(.semibold))
            TextField("open chrome or vision once check for a red error state", text: $viewModel.typedCommand)
                .onSubmit {
                    viewModel.submitTypedCommand()
                }
                .textFieldStyle(.roundedBorder)
                .disabled(viewModel.isSubmittingCommand)
            HStack {
                Button(viewModel.isSubmittingCommand ? "Sending..." : "Send") {
                    viewModel.submitTypedCommand()
                }
                .disabled(viewModel.isSubmittingCommand || viewModel.typedCommand.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                Button("Vision Once") {
                    viewModel.submitTypedCommand(asVision: true)
                }
                .disabled(viewModel.isSubmittingCommand || viewModel.typedCommand.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                if viewModel.isSubmittingCommand {
                    ProgressView()
                        .controlSize(.small)
                }
            }
            if !viewModel.commandError.isEmpty {
                Text(viewModel.commandError)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .lineLimit(3)
            }
        }
    }

    private var playerControls: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Player")
                .font(.subheadline.weight(.semibold))
            Text("\(mediaSessionManager.currentTitle) · \(mediaSessionManager.playerSurfaceState)")
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
            HStack {
                Button("Show Player") {
                    mediaSessionManager.showPlayer()
                }
                Button("Bootstrap") {
                    mediaSessionManager.loadBootstrapMedia()
                }
            }
            Text("Phase 1 uses one CALCIE-owned media surface and reuses the same window.")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var visionControls: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Vision Monitor")
                .font(.subheadline.weight(.semibold))
            Text(viewModel.visionGoal)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
            HStack {
                Button("Start Vision Monitor") {
                    viewModel.startVision()
                }
                Button("Stop Vision Monitor") {
                    viewModel.stopVision()
                }
            }
            Button("Edit in Settings") {
                viewModel.openAdvancedOptions()
            }
            .font(.caption)
        }
    }

    private var footer: some View {
        HStack {
            Text(viewModel.runtimeOnline ? "Runtime connected" : "Runtime offline")
                .font(.caption2)
                .foregroundStyle(viewModel.runtimeOnline ? .green : .red)
            Spacer()
            Text("Hold Right Option")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }
}

private struct ChatBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack(alignment: .top) {
            if message.isUser {
                Spacer(minLength: 42)
            }
            VStack(alignment: .leading, spacing: 4) {
                Text(message.isUser ? "you" : "CALCIE says")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text(message.text)
                    .font(message.isUser ? .body.weight(.medium) : .body)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(message.isUser ? Color.secondary.opacity(0.20) : Color.secondary.opacity(0.10))
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            if !message.isUser {
                Spacer(minLength: 42)
            }
        }
    }
}

struct AdvancedOptionsView: View {
    @ObservedObject var viewModel: ShellViewModel
    @ObservedObject var mediaSessionManager: MediaSessionManager

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                runtimeSection
                Divider()
                assistantSection
                Divider()
                profileImportSection
                Divider()
                updatesSection
                Divider()
                playerSection
                Divider()
                appBundleSection
                Divider()
                runtimeActions
                Divider()
                visionSettings
                Divider()
                recentEvents
                Divider()
                permissions
                Divider()
                startup
                if viewModel.developerToolsAvailable {
                    Divider()
                    developerToolsSection
                }
            }
            .padding(16)
        }
        .frame(minWidth: 430, minHeight: 620)
    }

    private var runtimeSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("CALCIE Settings")
                .font(.headline)
            Text("State: \(viewModel.runtimeState)")
                .font(.subheadline)
            if !viewModel.runtimeDetail.isEmpty {
                Text(viewModel.runtimeDetail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text("LLM: \(viewModel.activeLLM) | TTS: \(viewModel.ttsProvider)")
                .font(.caption2)
                .foregroundStyle(.secondary)
            if !viewModel.runtimeLaunchMessage.isEmpty {
                Text(viewModel.runtimeLaunchMessage)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            if viewModel.developerToolsAvailable && !viewModel.runtimeIdentityMessage.isEmpty {
                Text(viewModel.runtimeIdentityMessage)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var assistantSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Assistant")
                .font(.subheadline.weight(.semibold))
            if !viewModel.lastResponse.isEmpty {
                Text("Last Response")
                    .font(.caption.weight(.semibold))
                Text(viewModel.lastResponse)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if viewModel.developerToolsAvailable {
                Text("Model: \(viewModel.activeLLM)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text("TTS: \(viewModel.ttsProvider) · route: \(viewModel.lastRoute)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var profileImportSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("First-Run Memory Import")
                    .font(.subheadline.weight(.semibold))
                Spacer()
                Text(viewModel.hasChatGPTProfileImport ? "Imported" : "Optional")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(viewModel.hasChatGPTProfileImport ? .green : .secondary)
            }
            Text("For a fresh install, ask ChatGPT for a memory export, then paste the fenced response here. CALCIE stores it locally and does not upload it.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Text(viewModel.profileImportPrompt)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
                .padding(8)
                .background(Color.secondary.opacity(0.10), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            HStack {
                Button("Copy Prompt") {
                    viewModel.copyProfileImportPrompt()
                }
                Button("Refresh Status") {
                    Task { await viewModel.refreshProfileImportStatus() }
                }
            }
            TextEditor(text: $viewModel.profileImportText)
                .font(.caption)
                .frame(minHeight: 92)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Color.secondary.opacity(0.25))
                )
            HStack {
                Button(viewModel.profileImportInFlight ? "Importing..." : "Import ChatGPT Memory") {
                    viewModel.importChatGPTProfile()
                }
                .disabled(viewModel.profileImportInFlight || viewModel.profileImportText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                if viewModel.profileImportInFlight {
                    ProgressView()
                        .controlSize(.small)
                }
            }
            Text(viewModel.profileImportMessage)
                .font(.caption2)
                .foregroundStyle(viewModel.hasChatGPTProfileImport ? .green : .secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var updatesSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Updates")
                    .font(.subheadline.weight(.semibold))
                Spacer()
                Text(viewModel.updateAvailable ? "Available" : "Checked")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(viewModel.updateAvailable ? .orange : .secondary)
            }
            Text(viewModel.updateStatusMessage)
                .font(.caption)
                .foregroundStyle(viewModel.updateAvailable ? .orange : .secondary)
                .fixedSize(horizontal: false, vertical: true)
            if viewModel.updateAvailable {
                Text("Version \(viewModel.updateVersion) · build \(viewModel.updateBuild)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                if viewModel.updateRequired {
                    Text("This update is marked required.")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.red)
                }
            }
            HStack {
                Button(viewModel.updateCheckInFlight ? "Checking..." : "Check Now") {
                    Task { await viewModel.refreshUpdateStatus() }
                }
                .disabled(viewModel.updateCheckInFlight)
                Button("Download") {
                    viewModel.openUpdateDownload()
                }
                .disabled(!viewModel.updateAvailable || viewModel.updateDownloadURL.isEmpty)
                Button("Release Notes") {
                    viewModel.openUpdateReleaseNotes()
                }
                .disabled(viewModel.updateReleaseNotesURL.isEmpty)
            }
        }
    }

    private var playerSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("CALCIE Player")
                .font(.subheadline.weight(.semibold))
            Text("Surface: \(mediaSessionManager.playerSurfaceState)")
                .font(.caption)
            Text(mediaSessionManager.currentTitle)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(mediaSessionManager.currentSubtitle)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Text("Google session: \(mediaSessionManager.googleSessionState)")
                .font(.caption2)
                .foregroundStyle(.secondary)
            if !mediaSessionManager.currentURLString.isEmpty {
                Text(mediaSessionManager.currentURLString)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            HStack {
                Button("Open Player") {
                    mediaSessionManager.showPlayer()
                }
                Button("Reload Player") {
                    mediaSessionManager.reloadCurrentMedia()
                }
            }
            HStack {
                Button("Google Sign-In") {
                    mediaSessionManager.openGoogleSignIn(
                        for: mediaSessionManager.currentPlatform == "ytmusic" ? "ytmusic" : "youtube"
                    )
                }
                Button("Sign Out") {
                    mediaSessionManager.signOutGoogleSession()
                }
            }
            if viewModel.developerToolsAvailable {
                Text(mediaSessionManager.googleSessionDetail)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Text(mediaSessionManager.googleSessionFallbackHint)
                    .font(.caption2)
                    .foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
                HStack {
                    Button("Bootstrap Video") {
                        mediaSessionManager.loadBootstrapMedia()
                    }
                    Button("YouTube Login") {
                        mediaSessionManager.openGoogleSignIn(for: "youtube")
                    }
                    Button("Music Login") {
                        mediaSessionManager.openGoogleSignIn(for: "ytmusic")
                    }
                }
                HStack {
                    Button("Browser Login") {
                        mediaSessionManager.openGoogleSignInInBrowser(for: "youtube")
                    }
                }
            }
        }
    }

    private var appBundleSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("App Bundle")
                .font(.subheadline.weight(.semibold))
            Text(viewModel.appLocationMessage)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if !viewModel.appBundleSummary.isEmpty {
                Text(viewModel.appBundleSummary)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !viewModel.appBundleWarning.isEmpty {
                Text(viewModel.appBundleWarning)
                    .font(.caption2)
                    .foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var runtimeActions: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Developer Actions")
                .font(.subheadline.weight(.semibold))
            HStack {
                Button("Open Debug Terminal") {
                    viewModel.openDebugTerminal()
                }
                Button(viewModel.runtimeRestartInFlight ? "Restarting..." : "Restart Runtime") {
                    viewModel.restartRuntime()
                }
                .disabled(viewModel.runtimeRestartInFlight)
            }
            HStack {
                Button("Open Project Root") {
                    viewModel.openProjectRoot()
                }
            }
        }
    }

    private var developerToolsSection: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 12) {
                Text("Only shown in repo-backed builds so normal users don't have to see internal controls.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                appBundleSection
                runtimeActions
            }
            .padding(.top, 8)
        } label: {
            Text("Developer Tools")
                .font(.subheadline.weight(.semibold))
        }
    }

    private var visionSettings: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Vision Settings")
                .font(.subheadline.weight(.semibold))
            TextField("watch for terminal build failures", text: $viewModel.visionGoal)
                .textFieldStyle(.roundedBorder)
            Text("This goal is used when you start the vision monitor from the mini menu or here.")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var recentEvents: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Recent Events")
                .font(.subheadline.weight(.semibold))
            if viewModel.recentEvents.isEmpty {
                Text("No recent events yet.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(viewModel.recentEvents.prefix(4)) { event in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(event.summary)
                            .font(.caption)
                        Text("\(event.timestamp) · \(event.type)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    private var permissions: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Permissions Checklist")
                .font(.subheadline.weight(.semibold))
            ForEach(viewModel.nativePermissions) { permission in
                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Text(permission.name)
                            .font(.caption.weight(.semibold))
                        Spacer()
                        Text(permission.statusText)
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(permission.granted ? .green : .orange)
                    }
                    Text(permission.detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            if !viewModel.permissionWarnings.isEmpty {
                Text("Runtime Notes")
                    .font(.caption.weight(.semibold))
                    .padding(.top, 2)
                ForEach(viewModel.permissionWarnings, id: \.self) { warning in
                    Text("• \(warning)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            HStack {
                Button("Microphone") {
                    viewModel.handleMicrophonePermissionAction()
                }
                Button("Accessibility") {
                    viewModel.openPrivacyPane("Privacy_Accessibility")
                }
            }
            HStack {
                Button("Screen Recording") {
                    viewModel.openPrivacyPane("Privacy_ScreenCapture")
                }
                Button("Notifications") {
                    viewModel.handleNotificationPermissionAction()
                }
            }
        }
    }

    private var startup: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Startup")
                .font(.subheadline.weight(.semibold))
            Toggle(
                "Launch CALCIE at Login",
                isOn: Binding(
                    get: { viewModel.launchAtLoginEnabled },
                    set: { viewModel.setLaunchAtLogin($0) }
                )
            )
            .disabled(!viewModel.launchAtLoginAvailable)
            Text(viewModel.launchAtLoginMessage)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}
