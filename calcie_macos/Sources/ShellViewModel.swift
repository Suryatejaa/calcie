import AppKit
import AVFoundation
import Foundation
import ServiceManagement
import SwiftUI
import UserNotifications

struct NativePermissionStatus: Identifiable {
    let name: String
    let statusText: String
    let detail: String
    let granted: Bool

    var id: String { name }
}

private struct ShellWindowSnapshot: Encodable {
    let visible: Bool
    let frame: ShellWindowFrame?
    let desktop_bounds: ShellDesktopBounds?
    let screen_scale: Double
    let updated_at: String
}

private struct ShellWindowFrame: Encodable {
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

private struct ShellDesktopBounds: Encodable {
    let min_x: Double
    let min_y: Double
    let max_x: Double
    let max_y: Double
    let width: Double
    let height: Double
}

private struct ShellControlRequest: Decodable {
    let action: String
    let request_id: String?
    let requested_at: String?
}

private struct ShellRuntimeSnapshot: Encodable {
    let player_supported: Bool
    let bundle_path: String
    let repo_root: String
    let runtime_online: Bool
    let updated_at: String
}

private struct AppBundleRuntimeConfig: Decodable {
    let project_root: String?
    let build_configuration: String?
    let code_signing_style: String?
    let code_signing_identity: String?
    let built_at: String?
    let repo_backed: Bool?
}

@MainActor
final class ShellViewModel: ObservableObject {
    @Published var runtimeState = "offline"
    @Published var runtimeDetail = "Starting up"
    @Published var activeLLM = "-"
    @Published var ttsProvider = "-"
    @Published var lastRoute = "-"
    @Published var lastResponse = ""
    @Published var typedCommand = ""
    @Published var visionGoal = "watch for terminal build failures"
    @Published var recentEvents: [RuntimeEvent] = []
    @Published var permissionWarnings: [String] = []
    @Published var voiceSessionActive = false
    @Published var runtimeOnline = false
    @Published var runtimeLaunchMessage = ""
    @Published var isSubmittingCommand = false
    @Published var commandError = ""
    @Published var commandHint = "Try: open chrome, search latest AI news, vision once check for a red error state"
    @Published var launchAtLoginEnabled = false
    @Published var launchAtLoginAvailable = false
    @Published var launchAtLoginMessage = ""
    @Published var appLocationMessage = ""
    @Published var nativePermissions: [NativePermissionStatus] = []
    @Published var runtimeIdentityMessage = ""
    @Published var runtimeRestartInFlight = false
    @Published var appBundleSummary = ""
    @Published var appBundleWarning = ""

    private let client = LocalAPIClient()
    private var pollTimer: Timer?
    private var controlTimer: Timer?
    private var runtimeProcess: Process?
    private let repoRoot: String
    private let bundlePath: String
    private let appBundleConfig: AppBundleRuntimeConfig?
    private let shellWindowStatePath: URL
    private let shellControlRequestPath: URL
    private let shellStatusPath: URL
    private let mediaPlayerCommandPath: URL
    private weak var panelWindow: NSWindow?
    private var lastHandledControlRequestId = ""
    private var lastHandledMediaCommandId = ""
    private var suppressWindowSnapshotsUntil = Date.distantPast
    private var runtimeInstanceID = ""
    var dismissPanelHandler: (() -> Void)?
    var openAdvancedOptionsHandler: (() -> Void)?
    var mediaPlayerCommandHandler: ((MediaPlayerCommandRequest) -> Void)?

    init() {
        self.appBundleConfig = Self.loadAppBundleConfig()
        self.repoRoot = Self.discoverRepoRoot(config: self.appBundleConfig)
        self.bundlePath = Bundle.main.bundleURL.path
        self.shellWindowStatePath = URL(fileURLWithPath: self.repoRoot)
            .appendingPathComponent(".calcie/runtime/macos_shell_window.json")
        self.shellControlRequestPath = URL(fileURLWithPath: self.repoRoot)
            .appendingPathComponent(".calcie/runtime/macos_shell_control.json")
        self.shellStatusPath = URL(fileURLWithPath: self.repoRoot)
            .appendingPathComponent(".calcie/runtime/macos_shell_status.json")
        self.mediaPlayerCommandPath = URL(fileURLWithPath: self.repoRoot)
            .appendingPathComponent(".calcie/runtime/media_player_command.json")
        self.appLocationMessage = Self.describeAppLocation(bundlePath: self.bundlePath)
        self.appBundleSummary = Self.describeAppBundle(config: self.appBundleConfig, repoRoot: self.repoRoot)
        self.appBundleWarning = Self.appBundleWarning(config: self.appBundleConfig, repoRoot: self.repoRoot)
    }

    func start() {
        Task {
            await ensureRuntime()
            await refreshAll()
        }
        writeShellRuntimeStatus()
        refreshLaunchAtLoginStatus()
        pollTimer = Timer.scheduledTimer(withTimeInterval: 3.0, repeats: true) { [weak self] _ in
            guard let self else { return }
            Task { await self.refreshAll() }
        }
        controlTimer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.processShellControlRequestIfNeeded()
                self?.processMediaPlayerCommandIfNeeded()
            }
        }
    }

    func stop() {
        pollTimer?.invalidate()
        pollTimer = nil
        controlTimer?.invalidate()
        controlTimer = nil
        writeShellRuntimeStatus()
    }

    func refreshAll() async {
        do {
            let status = try await client.status()
            applyRuntimeStatus(status)
        } catch {
            runtimeOnline = false
            runtimeState = "offline"
            runtimeDetail = error.localizedDescription
            runtimeIdentityMessage = ""
        }

        await refreshNativePermissionStatus()
        writeShellRuntimeStatus()

        do {
            recentEvents = try await client.events(limit: 8)
        } catch {
            if recentEvents.isEmpty {
                recentEvents = []
            }
        }
    }

    func ensureRuntime() async {
        do {
            let health = try await client.health()
            if runtimeMatchesExpectedRoot(health.runtime_project_root) {
                runtimeLaunchMessage = "Runtime already running."
                runtimeOnline = true
                return
            }
            runtimeOnline = false
            runtimeState = "error"
            runtimeDetail = "Connected runtime belongs to a different project."
            runtimeLaunchMessage = "Expected CALCIE runtime at \(repoRoot), but found \(health.runtime_project_root ?? "unknown")."
            runtimeIdentityMessage = runtimeIdentityLine(
                projectRoot: health.runtime_project_root,
                pid: health.runtime_pid,
                instanceID: health.runtime_instance_id,
                startedAt: health.runtime_started_at
            )
            return
        } catch {
            launchRuntimeProcess()
            try? await Task.sleep(for: .seconds(2))
        }
    }

    func submitTypedCommand() {
        let command = typedCommand.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !command.isEmpty, !isSubmittingCommand else { return }
        isSubmittingCommand = true
        commandError = ""
        lastResponse = "Working on: \(command)"
        lastRoute = "-"
        runtimeState = "thinking"
        runtimeDetail = "Sending command to CALCIE..."
        typedCommand = ""
        Task {
            defer { isSubmittingCommand = false }
            do {
                let response = try await client.command(command)
                runtimeState = response.state ?? "idle"
                runtimeDetail = response.ok ? "Command handled." : "Command reported an issue."
                if let route = response.route, !route.isEmpty {
                    lastRoute = route
                }
                lastResponse = response.response
                if !response.ok {
                    commandError = response.response
                }
                await refreshAll()
            } catch {
                let message = "Command failed: \(error.localizedDescription)"
                lastResponse = message
                commandError = message
                runtimeState = "error"
                runtimeDetail = error.localizedDescription
            }
        }
    }

    func toggleVoice() {
        Task {
            do {
                if voiceSessionActive {
                    let response = try await client.stopVoice()
                    runtimeState = response.state ?? "idle"
                } else {
                    let response = try await client.startVoice()
                    runtimeState = response.state ?? "listening"
                }
                await refreshAll()
            } catch {
                runtimeState = "error"
                runtimeDetail = error.localizedDescription
            }
        }
    }

    func startVoiceSession() {
        guard !voiceSessionActive else { return }
        Task {
            do {
                let response = try await client.startVoice()
                runtimeState = response.state ?? "listening"
                await refreshAll()
            } catch {
                runtimeState = "error"
                runtimeDetail = error.localizedDescription
            }
        }
    }

    func stopVoiceSession() {
        guard voiceSessionActive else { return }
        Task {
            do {
                let response = try await client.stopVoice()
                runtimeState = response.state ?? "idle"
                await refreshAll()
            } catch {
                runtimeState = "error"
                runtimeDetail = error.localizedDescription
            }
        }
    }

    func startVision() {
        let goal = visionGoal.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !goal.isEmpty else { return }
        Task {
            do {
                let response = try await client.startVision(goal: goal)
                lastResponse = response.response
                runtimeState = response.state ?? "vision_monitoring"
                await refreshAll()
            } catch {
                runtimeState = "error"
                runtimeDetail = error.localizedDescription
            }
        }
    }

    func stopVision() {
        Task {
            do {
                let response = try await client.stopVision()
                lastResponse = response.response
                runtimeState = response.state ?? "idle"
                await refreshAll()
            } catch {
                runtimeState = "error"
                runtimeDetail = error.localizedDescription
            }
        }
    }

    func restartRuntime() {
        guard !runtimeRestartInFlight else { return }
        runtimeRestartInFlight = true
        runtimeLaunchMessage = "Restarting CALCIE runtime..."
        Task {
            defer { runtimeRestartInFlight = false }
            if let runtimeProcess, runtimeProcess.isRunning {
                runtimeProcess.terminate()
                self.runtimeProcess = nil
                try? await Task.sleep(for: .seconds(1))
                launchRuntimeProcess()
                try? await Task.sleep(for: .seconds(2))
                await refreshAll()
                runtimeLaunchMessage = "Shell-owned runtime restarted."
                return
            }
            do {
                let response = try await client.restartRuntime()
                runtimeState = response.state ?? "starting"
                runtimeDetail = response.response
                try? await Task.sleep(for: .seconds(2))
                await refreshAll()
                runtimeLaunchMessage = "Runtime restart requested."
            } catch {
                runtimeLaunchMessage = "Runtime restart failed: \(error.localizedDescription)"
                runtimeState = "error"
                runtimeDetail = error.localizedDescription
            }
        }
    }

    func openDebugTerminal() {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        process.arguments = ["-a", "Terminal", repoRoot]
        try? process.run()
    }

    func openProjectRoot() {
        NSWorkspace.shared.open(URL(fileURLWithPath: repoRoot))
    }

    func openPrivacyPane(_ anchor: String) {
        guard let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?\(anchor)") else {
            return
        }
        NSWorkspace.shared.open(url)
    }

    func handleMicrophonePermissionAction() {
        let status = AVCaptureDevice.authorizationStatus(for: .audio)
        switch status {
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .audio) { [weak self] granted in
                Task { @MainActor in
                    await self?.refreshNativePermissionStatus()
                    if granted {
                        self?.runtimeDetail = "Microphone permission granted."
                    } else {
                        self?.runtimeDetail = "Microphone permission was denied."
                    }
                }
            }
        default:
            openPrivacyPane("Privacy_Microphone")
        }
    }

    func handleNotificationPermissionAction() {
        Task { @MainActor in
            let currentStatus: UNAuthorizationStatus = await withCheckedContinuation { continuation in
                UNUserNotificationCenter.current().getNotificationSettings { settings in
                    continuation.resume(returning: settings.authorizationStatus)
                }
            }
            switch currentStatus {
            case .notDetermined:
                do {
                    let granted = try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound])
                    await refreshNativePermissionStatus()
                    runtimeDetail = granted
                        ? "Notification permission granted."
                        : "Notification permission was denied."
                } catch {
                    runtimeDetail = "Notification permission request failed: \(error.localizedDescription)"
                }
            default:
                openPrivacyPane("Notifications")
            }
        }
    }

    private func refreshNativePermissionStatus() async {
        let microphone = microphonePermissionStatus()
        let accessibility = accessibilityPermissionStatus()
        let screenRecording = screenRecordingPermissionStatus()
        let notifications = await notificationPermissionStatus()
        nativePermissions = [
            microphone,
            accessibility,
            screenRecording,
            notifications,
        ]
    }

    private func microphonePermissionStatus() -> NativePermissionStatus {
        let status = AVCaptureDevice.authorizationStatus(for: .audio)
        switch status {
        case .authorized:
            return NativePermissionStatus(
                name: "Microphone",
                statusText: "Granted",
                detail: "CALCIE can listen when you use talk-to-CALCIE.",
                granted: true
            )
        case .notDetermined:
            return NativePermissionStatus(
                name: "Microphone",
                statusText: "Not requested",
                detail: "Open talk-to-CALCIE once and macOS should prompt for microphone access.",
                granted: false
            )
        case .denied:
            return NativePermissionStatus(
                name: "Microphone",
                statusText: "Denied",
                detail: "Enable CALCIE in Privacy & Security > Microphone.",
                granted: false
            )
        case .restricted:
            return NativePermissionStatus(
                name: "Microphone",
                statusText: "Restricted",
                detail: "Microphone access is restricted by macOS or device policy.",
                granted: false
            )
        @unknown default:
            return NativePermissionStatus(
                name: "Microphone",
                statusText: "Unknown",
                detail: "CALCIE could not determine microphone permission status.",
                granted: false
            )
        }
    }

    private func accessibilityPermissionStatus() -> NativePermissionStatus {
        let trusted = AXIsProcessTrusted()
        return NativePermissionStatus(
            name: "Accessibility",
            statusText: trusted ? "Granted" : "Missing",
            detail: trusted
                ? "Desktop control can send input events when needed."
                : "Enable CALCIE in Privacy & Security > Accessibility for input control.",
            granted: trusted
        )
    }

    private func screenRecordingPermissionStatus() -> NativePermissionStatus {
        let granted = CGPreflightScreenCaptureAccess()
        return NativePermissionStatus(
            name: "Screen Recording",
            statusText: granted ? "Granted" : "Missing",
            detail: granted
                ? "Vision and screenshot capture can inspect the screen."
                : "Enable CALCIE in Privacy & Security > Screen Recording for vision tasks.",
            granted: granted
        )
    }

    private func notificationPermissionStatus() async -> NativePermissionStatus {
        let authorizationStatus: UNAuthorizationStatus = await withCheckedContinuation { continuation in
            UNUserNotificationCenter.current().getNotificationSettings { settings in
                continuation.resume(returning: settings.authorizationStatus)
            }
        }
        switch authorizationStatus {
        case .authorized, .provisional, .ephemeral:
            return NativePermissionStatus(
                name: "Notifications",
                statusText: "Granted",
                detail: "CALCIE can surface alerts outside the menu bar when needed.",
                granted: true
            )
        case .notDetermined:
            return NativePermissionStatus(
                name: "Notifications",
                statusText: "Not requested",
                detail: "Notifications have not been requested yet for CALCIE.app.",
                granted: false
            )
        case .denied:
            return NativePermissionStatus(
                name: "Notifications",
                statusText: "Denied",
                detail: "Enable CALCIE in Notifications if you want desktop alerts.",
                granted: false
            )
        @unknown default:
            return NativePermissionStatus(
                name: "Notifications",
                statusText: "Unknown",
                detail: "CALCIE could not determine notification permission status.",
                granted: false
            )
        }
    }

    func setLaunchAtLogin(_ enabled: Bool) {
        let service = SMAppService.mainApp
        do {
            if enabled {
                try service.register()
            } else {
                try service.unregister()
            }
            refreshLaunchAtLoginStatus()
            launchAtLoginMessage = enabled
                ? "CALCIE will launch when you sign in."
                : "Launch at login is turned off."
        } catch {
            refreshLaunchAtLoginStatus()
            launchAtLoginMessage = "Launch at login update failed: \(error.localizedDescription)"
        }
    }

    func openAdvancedOptions() {
        openAdvancedOptionsHandler?()
    }

    func updatePanelFrame(_ window: NSWindow?) {
        guard let window else { return }
        panelWindow = window
        if Date() < suppressWindowSnapshotsUntil {
            return
        }
        let frame = window.frame
        let screens = NSScreen.screens.map(\.frame)
        let minX = screens.map(\.minX).min() ?? frame.minX
        let minY = screens.map(\.minY).min() ?? frame.minY
        let maxX = screens.map(\.maxX).max() ?? frame.maxX
        let maxY = screens.map(\.maxY).max() ?? frame.maxY
        let scale = window.screen?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 1.0
        let snapshot = ShellWindowSnapshot(
            visible: true,
            frame: ShellWindowFrame(
                x: frame.minX,
                y: frame.minY,
                width: frame.width,
                height: frame.height
            ),
            desktop_bounds: ShellDesktopBounds(
                min_x: minX,
                min_y: minY,
                max_x: maxX,
                max_y: maxY,
                width: maxX - minX,
                height: maxY - minY
            ),
            screen_scale: scale,
            updated_at: ISO8601DateFormatter().string(from: Date())
        )
        writeShellWindowState(snapshot)
    }

    func clearPanelFrame() {
        panelWindow = nil
        let snapshot = ShellWindowSnapshot(
            visible: false,
            frame: nil,
            desktop_bounds: nil,
            screen_scale: 1.0,
            updated_at: ISO8601DateFormatter().string(from: Date())
        )
        writeShellWindowState(snapshot)
    }

    private func launchRuntimeProcess() {
        if runtimeProcess?.isRunning == true {
            return
        }
        let process = Process()
        process.currentDirectoryURL = URL(fileURLWithPath: repoRoot)
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = [
            "python3",
            "-m",
            "calcie_local_api.server",
        ]
        var env = ProcessInfo.processInfo.environment
        env["CALCIE_PROJECT_ROOT"] = repoRoot
        process.environment = env
        process.standardOutput = Pipe()
        process.standardError = Pipe()
        do {
            try process.run()
            runtimeProcess = process
            runtimeLaunchMessage = "Started local CALCIE runtime."
        } catch {
            runtimeLaunchMessage = "Failed to launch runtime: \(error.localizedDescription)"
        }
    }

    private func applyRuntimeStatus(_ status: RuntimeStatus) {
        let matchesRoot = runtimeMatchesExpectedRoot(status.runtime_project_root)
        runtimeOnline = matchesRoot
        runtimeState = matchesRoot ? status.state : "error"
        runtimeDetail = matchesRoot ? status.detail : "Connected runtime belongs to a different project."
        activeLLM = status.active_llm
        ttsProvider = status.tts_provider_mode
        lastRoute = status.last_route.isEmpty ? "-" : status.last_route
        lastResponse = status.last_response
        permissionWarnings = status.permission_warnings
        voiceSessionActive = status.voice_session_active ?? false
        runtimeInstanceID = status.runtime_instance_id ?? ""
        runtimeIdentityMessage = runtimeIdentityLine(
            projectRoot: status.runtime_project_root,
            pid: status.runtime_pid,
            instanceID: status.runtime_instance_id,
            startedAt: status.runtime_started_at
        )
        if !status.current_monitor_goal.isEmpty {
            visionGoal = status.current_monitor_goal
        }
        if !status.last_response.isEmpty {
            commandError = ""
        }
        if matchesRoot {
            if let pid = status.runtime_pid {
                runtimeLaunchMessage = "Runtime connected (pid \(pid))."
            } else {
                runtimeLaunchMessage = "Runtime connected."
            }
        } else {
            runtimeLaunchMessage = "This app expects runtime root \(repoRoot), but connected runtime root is \(status.runtime_project_root ?? "unknown")."
        }
    }

    private func runtimeMatchesExpectedRoot(_ remoteRoot: String?) -> Bool {
        guard let remoteRoot else { return true }
        return Self.normalizePath(remoteRoot) == Self.normalizePath(repoRoot)
    }

    private func runtimeIdentityLine(projectRoot: String?, pid: Int?, instanceID: String?, startedAt: String?) -> String {
        let root = projectRoot.map(Self.normalizePath) ?? "unknown"
        let pidText = pid.map(String.init) ?? "-"
        let shortID: String
        if let instanceID, !instanceID.isEmpty {
            shortID = String(instanceID.prefix(8))
        } else {
            shortID = "-"
        }
        let started = startedAt ?? "-"
        return "Runtime: pid \(pidText) · id \(shortID) · started \(started) · root \(root)"
    }

    private func refreshLaunchAtLoginStatus() {
        let runningFromApplications = Self.isApplicationsInstallPath(bundlePath)
        let status = SMAppService.mainApp.status
        switch status {
        case .enabled:
            launchAtLoginEnabled = true
            launchAtLoginAvailable = true
            if launchAtLoginMessage.isEmpty {
                launchAtLoginMessage = "CALCIE launches at sign-in."
            }
        case .requiresApproval:
            launchAtLoginEnabled = false
            launchAtLoginAvailable = true
            launchAtLoginMessage = "macOS needs approval before CALCIE can launch at sign-in."
        case .notFound:
            launchAtLoginEnabled = false
            launchAtLoginAvailable = runningFromApplications
            if runningFromApplications {
                launchAtLoginMessage = "CALCIE is installed, but this instance may be stale. Quit other CALCIE copies, then reopen CALCIE.app from Applications."
            } else {
                launchAtLoginMessage = "Open CALCIE.app from Applications to enable launch at login."
            }
        case .notRegistered:
            launchAtLoginEnabled = false
            launchAtLoginAvailable = runningFromApplications
            if launchAtLoginMessage.isEmpty || launchAtLoginMessage == "CALCIE launches at sign-in." {
                launchAtLoginMessage = runningFromApplications
                    ? "Launch at login is available."
                    : "Open CALCIE.app from Applications to enable launch at login."
            }
        @unknown default:
            launchAtLoginEnabled = false
            launchAtLoginAvailable = false
            launchAtLoginMessage = "Launch at login status is unavailable on this build."
        }
    }

    private static func isApplicationsInstallPath(_ bundlePath: String) -> Bool {
        let normalized = NSString(string: bundlePath).standardizingPath
        let userApplications = NSString(string: "~/Applications").expandingTildeInPath
        return normalized.hasPrefix("/Applications/") || normalized.hasPrefix(userApplications + "/")
    }

    private static func describeAppLocation(bundlePath: String) -> String {
        let normalized = NSString(string: bundlePath).standardizingPath
        if isApplicationsInstallPath(normalized) {
            return "App location: \(normalized)"
        }
        return "Current build is running from \(normalized). For launch at login, quit this copy and open CALCIE.app from Applications."
    }

    private func writeShellWindowState(_ snapshot: ShellWindowSnapshot) {
        do {
            let parent = shellWindowStatePath.deletingLastPathComponent()
            try FileManager.default.createDirectory(at: parent, withIntermediateDirectories: true)
            let data = try JSONEncoder().encode(snapshot)
            try data.write(to: shellWindowStatePath, options: .atomic)
        } catch {
            runtimeLaunchMessage = "Window state write failed: \(error.localizedDescription)"
        }
    }

    private func writeShellRuntimeStatus() {
        let snapshot = ShellRuntimeSnapshot(
            player_supported: true,
            bundle_path: bundlePath,
            repo_root: repoRoot,
            runtime_online: runtimeOnline,
            updated_at: ISO8601DateFormatter().string(from: Date())
        )
        do {
            let parent = shellStatusPath.deletingLastPathComponent()
            try FileManager.default.createDirectory(at: parent, withIntermediateDirectories: true)
            let data = try JSONEncoder().encode(snapshot)
            try data.write(to: shellStatusPath, options: .atomic)
        } catch {
            runtimeLaunchMessage = "Shell status write failed: \(error.localizedDescription)"
        }
    }

    private func processShellControlRequestIfNeeded() {
        guard FileManager.default.fileExists(atPath: shellControlRequestPath.path) else {
            return
        }
        let request: ShellControlRequest
        do {
            let data = try Data(contentsOf: shellControlRequestPath)
            request = try JSONDecoder().decode(ShellControlRequest.self, from: data)
        } catch {
            try? FileManager.default.removeItem(at: shellControlRequestPath)
            return
        }

        if let requestID = request.request_id, requestID == lastHandledControlRequestId {
            try? FileManager.default.removeItem(at: shellControlRequestPath)
            return
        }

        if request.action == "dismiss_panel" {
            dismissPanel()
        }
        if let requestID = request.request_id {
            lastHandledControlRequestId = requestID
        }
        try? FileManager.default.removeItem(at: shellControlRequestPath)
    }

    private func processMediaPlayerCommandIfNeeded() {
        guard FileManager.default.fileExists(atPath: mediaPlayerCommandPath.path) else {
            return
        }
        let request: MediaPlayerCommandRequest
        do {
            let data = try Data(contentsOf: mediaPlayerCommandPath)
            request = try JSONDecoder().decode(MediaPlayerCommandRequest.self, from: data)
        } catch {
            try? FileManager.default.removeItem(at: mediaPlayerCommandPath)
            return
        }

        if let requestID = request.request_id, requestID == lastHandledMediaCommandId {
            try? FileManager.default.removeItem(at: mediaPlayerCommandPath)
            return
        }

        mediaPlayerCommandHandler?(request)
        if let requestID = request.request_id {
            lastHandledMediaCommandId = requestID
        }
        try? FileManager.default.removeItem(at: mediaPlayerCommandPath)
    }

    private func dismissPanel() {
        suppressWindowSnapshotsUntil = Date().addingTimeInterval(1.5)
        clearPanelFrame()
        if let dismissPanelHandler {
            dismissPanelHandler()
            return
        }
        let windows = NSApp.windows
        for window in windows where window.isVisible {
            window.orderOut(nil)
            window.close()
        }
        panelWindow?.orderOut(nil)
        panelWindow?.close()
    }

    private static func discoverRepoRoot(config: AppBundleRuntimeConfig?) -> String {
        if let configured = ProcessInfo.processInfo.environment["CALCIE_PROJECT_ROOT"],
           !configured.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return configured
        }

        if let configured = config?.project_root?.trimmingCharacters(in: .whitespacesAndNewlines),
           !configured.isEmpty {
            return configured
        }

        let fallbackCandidates = [
            FileManager.default.currentDirectoryPath,
            URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().path,
        ]

        for candidate in fallbackCandidates {
            let root = URL(fileURLWithPath: candidate)
            if FileManager.default.fileExists(atPath: root.appendingPathComponent("calcie.py").path) {
                return root.path
            }
        }

        return FileManager.default.currentDirectoryPath
    }

    private static func normalizePath(_ path: String) -> String {
        NSString(string: path).standardizingPath
    }

    private static func loadAppBundleConfig() -> AppBundleRuntimeConfig? {
        guard let resourceURL = Bundle.main.resourceURL else { return nil }
        let configURL = resourceURL.appendingPathComponent("calcie_app_config.json")
        guard let data = try? Data(contentsOf: configURL) else { return nil }
        return try? JSONDecoder().decode(AppBundleRuntimeConfig.self, from: data)
    }

    private static func describeAppBundle(config: AppBundleRuntimeConfig?, repoRoot: String) -> String {
        let buildConfiguration = config?.build_configuration ?? "unknown"
        let signingStyle = (config?.code_signing_style ?? "unknown").uppercased()
        let builtAt = config?.built_at ?? "unknown"
        let repoBacked = (config?.repo_backed ?? true) ? "repo-backed" : "bundled runtime"
        return "Build: \(buildConfiguration) · signing \(signingStyle) · built \(builtAt) · \(repoBacked) · root \(repoRoot)"
    }

    private static func appBundleWarning(config: AppBundleRuntimeConfig?, repoRoot: String) -> String {
        let normalizedRoot = normalizePath(repoRoot)
        let rootURL = URL(fileURLWithPath: normalizedRoot)
        let hasRuntime = FileManager.default.fileExists(atPath: rootURL.appendingPathComponent("calcie.py").path)
        let signingStyle = (config?.code_signing_style ?? "ad-hoc").lowercased()
        if !hasRuntime {
            return "Configured project root is missing `calcie.py`, so the packaged app cannot launch the local runtime from this location."
        }
        if signingStyle != "stable" {
            return "This build is ad-hoc signed. macOS privacy permissions can reset after reinstall until CALCIE.app is signed with a stable identity."
        }
        return ""
    }
}
