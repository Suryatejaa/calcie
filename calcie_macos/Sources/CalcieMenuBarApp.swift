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
            .frame(width: 360)

        popover.behavior = .transient
        popover.animates = false
        popover.delegate = self
        popover.contentSize = NSSize(width: 388, height: 330)
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
            panel.title = "CALCIE Advanced Options"
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
        let systemName: String
        switch state {
        case "listening":
            systemName = "mic.fill"
        case "thinking":
            systemName = "brain.head.profile"
        case "speaking":
            systemName = "waveform"
        case "vision_monitoring":
            systemName = "eye.fill"
        case "error", "needs_permission":
            systemName = "exclamationmark.triangle.fill"
        default:
            systemName = "sparkles"
        }
        let image = NSImage(systemSymbolName: systemName, accessibilityDescription: "CALCIE")
        image?.isTemplate = true
        return image
    }
}

struct MenuBarContentView: View {
    @ObservedObject var viewModel: ShellViewModel
    @ObservedObject var mediaSessionManager: MediaSessionManager

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            Divider()
            quickActions
            Divider()
            typedCommand
            Divider()
            playerControls
            Divider()
            visionControls
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
                Button("Advanced Options") {
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
            TextField("open chrome", text: $viewModel.typedCommand)
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
            Button("Edit in Advanced Options") {
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
            }
            .padding(16)
        }
        .frame(minWidth: 430, minHeight: 620)
    }

    private var runtimeSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("CALCIE Advanced")
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
            if !viewModel.runtimeIdentityMessage.isEmpty {
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
            Text("Model: \(viewModel.activeLLM)")
                .font(.caption)
            Text("TTS: \(viewModel.ttsProvider)")
                .font(.caption)
                .foregroundStyle(.secondary)
            if !viewModel.lastResponse.isEmpty {
                Divider()
                Text("Last Response")
                    .font(.caption.weight(.semibold))
                Text(viewModel.lastResponse)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text("Last route: \(viewModel.lastRoute)")
                .font(.caption2)
                .foregroundStyle(.secondary)
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
                Button("Bootstrap Video") {
                    mediaSessionManager.loadBootstrapMedia()
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
            HStack {
                Button("Open Project Root") {
                    viewModel.openProjectRoot()
                }
            }
        }
    }

    private var runtimeActions: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Advanced Actions")
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
                Button("Quit CALCIE") {
                    NSApplication.shared.terminate(nil)
                }
            }
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
