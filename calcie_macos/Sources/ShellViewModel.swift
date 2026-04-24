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

struct ChatMessage: Identifiable {
    let id = UUID()
    let role: String
    let text: String
    let timestamp: Date

    var isUser: Bool {
        role == "user"
    }
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
    let cloud_base_url: String?
    let release_channel: String?
}

private struct UpdateManifestEnvelope: Decodable {
    let ok: Bool
    let update_available: Bool
    let release: UpdateRelease?
}

private struct UpdateRelease: Decodable {
    let platform: String
    let channel: String
    let version: String
    let build: String
    let download_url: String
    let sha256: String
    let release_notes_url: String
    let minimum_os: String
    let required: Bool
    let created_at: String
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
    @Published var chatInput = ""
    @Published var chatMessages: [ChatMessage] = []
    @Published var profileImportPrompt = "Return everything you know about me inside one fenced code block. Include long-term memory, bio details, and any model-set context you have with dates when available. I want a thorough memory export of what you've learned about me. Skip tool details and include only information that is actually about me. Be exhaustive and careful."
    @Published var profileImportText = ""
    @Published var profileImportMessage = "No ChatGPT memory import yet."
    @Published var profileImportInFlight = false
    @Published var hasChatGPTProfileImport = false
    @Published var profileImportChars = 0
    @Published var updateStatusMessage = "Update check has not run yet."
    @Published var updateAvailable = false
    @Published var updateVersion = ""
    @Published var updateBuild = ""
    @Published var updateDownloadURL = ""
    @Published var updateReleaseNotesURL = ""
    @Published var updateRequired = false
    @Published var updateCheckInFlight = false

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
    private let cloudBaseURL: String
    private let releaseChannel: String
    private weak var panelWindow: NSWindow?
    private var lastHandledControlRequestId = ""
    private var lastHandledMediaCommandId = ""
    private var suppressWindowSnapshotsUntil = Date.distantPast
    private var runtimeInstanceID = ""
    private var lastChatRuntimeResponse = ""
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
        self.cloudBaseURL = Self.discoverCloudBaseURL(config: self.appBundleConfig)
        self.releaseChannel = Self.discoverReleaseChannel(config: self.appBundleConfig)
        self.appLocationMessage = Self.describeAppLocation(bundlePath: self.bundlePath)
        self.appBundleSummary = Self.describeAppBundle(config: self.appBundleConfig, repoRoot: self.repoRoot)
        self.appBundleWarning = Self.appBundleWarning(config: self.appBundleConfig, repoRoot: self.repoRoot)
        self.chatMessages = [
            ChatMessage(
                role: "assistant",
                text: "Ask CALCIE anything, or use hold-to-talk. I’ll keep the latest responses here in case you miss the audio.",
                timestamp: Date()
            )
        ]
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
        await refreshUpdateStatusIfNeeded()
    }

    func refreshProfileImportStatus() async {
        do {
            applyProfileImportStatus(try await client.profileImportStatus())
        } catch {
            profileImportMessage = "Profile import status unavailable: \(error.localizedDescription)"
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

    func submitTypedCommand(asVision: Bool = false) {
        let rawCommand = typedCommand.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !rawCommand.isEmpty, !isSubmittingCommand else { return }
        typedCommand = ""
        submitCommand(resolvedCommandText(rawCommand, asVision: asVision), addToChat: false)
    }

    func submitChatMessage(asVision: Bool = false) {
        let rawCommand = chatInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !rawCommand.isEmpty, !isSubmittingCommand else { return }
        chatInput = ""
        submitCommand(resolvedCommandText(rawCommand, asVision: asVision), addToChat: true)
    }

    func clearChat() {
        chatMessages = [
            ChatMessage(
                role: "assistant",
                text: "Cleared. Ask a follow-up whenever you’re ready.",
                timestamp: Date()
            )
        ]
        lastChatRuntimeResponse = ""
        commandError = ""
    }

    private func submitCommand(_ command: String, addToChat: Bool) {
        guard !command.isEmpty, !isSubmittingCommand else { return }
        isSubmittingCommand = true
        commandError = ""
        lastResponse = "Working on: \(command)"
        lastRoute = "-"
        runtimeState = "thinking"
        runtimeDetail = "Sending command to CALCIE..."
        if addToChat {
            appendChatMessage(role: "user", text: command)
            appendChatMessage(role: "assistant", text: "Thinking...")
        }
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
                if addToChat {
                    replaceLastThinkingMessage(with: response.response)
                    lastChatRuntimeResponse = response.response
                }
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
                if addToChat {
                    replaceLastThinkingMessage(with: message)
                    lastChatRuntimeResponse = message
                }
            }
        }
    }

    private func resolvedCommandText(_ raw: String, asVision: Bool) -> String {
        let command = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard asVision else { return command }
        let normalized = command.lowercased()
        if normalized.hasPrefix("vision ") {
            return command
        }
        return "vision once \(command)"
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

    func refreshUpdateStatus() async {
        guard !updateCheckInFlight else { return }
        let base = cloudBaseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !base.isEmpty, let baseURL = URL(string: base) else {
            updateStatusMessage = "Update check is not configured. Set CALCIE_CLOUD_BASE_URL or CALCIE_SYNC_BASE_URL before building."
            updateAvailable = false
            return
        }

        updateCheckInFlight = true
        defer { updateCheckInFlight = false }

        var components = URLComponents(url: baseURL.appendingPathComponent("updates/latest"), resolvingAgainstBaseURL: false)
        components?.queryItems = [
            URLQueryItem(name: "platform", value: "macos"),
            URLQueryItem(name: "channel", value: releaseChannel),
        ]
        guard let url = components?.url else {
            updateStatusMessage = "Could not build update check URL."
            updateAvailable = false
            return
        }

        do {
            let (data, response) = try await URLSession.shared.data(from: url)
            if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
                updateStatusMessage = "Update check failed with HTTP \(http.statusCode)."
                updateAvailable = false
                return
            }
            let envelope = try JSONDecoder().decode(UpdateManifestEnvelope.self, from: data)
            applyUpdateManifest(envelope)
        } catch {
            updateStatusMessage = "Update check failed: \(error.localizedDescription)"
            updateAvailable = false
        }
    }

    func openUpdateDownload() {
        guard let url = URL(string: updateDownloadURL), !updateDownloadURL.isEmpty else { return }
        NSWorkspace.shared.open(url)
    }

    func openUpdateReleaseNotes() {
        guard let url = URL(string: updateReleaseNotesURL), !updateReleaseNotesURL.isEmpty else { return }
        NSWorkspace.shared.open(url)
    }

    func copyProfileImportPrompt() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(profileImportPrompt, forType: .string)
        profileImportMessage = "Prompt copied. Paste it into ChatGPT, then paste the fenced response here."
    }

    func importChatGPTProfile() {
        let text = profileImportText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !profileImportInFlight else { return }
        profileImportInFlight = true
        profileImportMessage = "Importing ChatGPT memory export..."
        Task {
            defer { profileImportInFlight = false }
            do {
                let response = try await client.importChatGPTProfile(text: text)
                profileImportMessage = response.response
                hasChatGPTProfileImport = response.ok
                profileImportChars = response.imported_chars ?? profileImportChars
                if response.ok {
                    profileImportText = ""
                }
                await refreshAll()
            } catch {
                profileImportMessage = "Import failed: \(error.localizedDescription)"
            }
        }
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
        if let profileImport = status.profile_import {
            applyProfileImportStatus(profileImport)
        }
        if !status.last_response.isEmpty {
            commandError = ""
            if status.last_response != lastChatRuntimeResponse {
                appendChatMessage(role: "assistant", text: status.last_response)
                lastChatRuntimeResponse = status.last_response
            }
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

    private func applyProfileImportStatus(_ status: ProfileImportStatus) {
        profileImportPrompt = status.import_prompt
        hasChatGPTProfileImport = status.has_chatgpt_import
        profileImportChars = status.imported_chars
        if status.has_chatgpt_import {
            let when = status.imported_at.isEmpty ? "previously" : status.imported_at
            profileImportMessage = "ChatGPT memory import loaded (\(status.imported_chars) chars, \(when))."
        } else if status.has_profile {
            profileImportMessage = "Profile template is present, but no ChatGPT memory import yet."
        } else {
            profileImportMessage = "No ChatGPT memory import yet."
        }
    }

    private func refreshUpdateStatusIfNeeded() async {
        if updateCheckInFlight {
            return
        }
        if updateStatusMessage == "Update check has not run yet." {
            await refreshUpdateStatus()
        }
    }

    private func applyUpdateManifest(_ envelope: UpdateManifestEnvelope) {
        guard envelope.ok else {
            updateAvailable = false
            updateStatusMessage = "Update service returned an error."
            return
        }
        guard envelope.update_available, let release = envelope.release else {
            updateAvailable = false
            updateStatusMessage = "CALCIE is up to date on \(releaseChannel)."
            return
        }

        let currentVersion = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0.0.0"
        let currentBuild = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "0"
        updateVersion = release.version
        updateBuild = release.build
        updateDownloadURL = release.download_url
        updateReleaseNotesURL = release.release_notes_url
        updateRequired = release.required
        updateAvailable = Self.releaseIsNewer(
            remoteVersion: release.version,
            remoteBuild: release.build,
            currentVersion: currentVersion,
            currentBuild: currentBuild
        )
        if updateAvailable {
            let requiredText = release.required ? " Required update." : ""
            updateStatusMessage = "CALCIE \(release.version) build \(release.build) is available on \(release.channel).\(requiredText)"
        } else {
            updateStatusMessage = "No newer update on \(release.channel). Current: \(currentVersion) build \(currentBuild)."
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

    private static func discoverCloudBaseURL(config: AppBundleRuntimeConfig?) -> String {
        if let configured = ProcessInfo.processInfo.environment["CALCIE_CLOUD_BASE_URL"],
           !configured.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return configured
        }
        if let configured = ProcessInfo.processInfo.environment["CALCIE_SYNC_BASE_URL"],
           !configured.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return configured
        }
        if let configured = config?.cloud_base_url?.trimmingCharacters(in: .whitespacesAndNewlines),
           !configured.isEmpty {
            return configured
        }
        return "https://calcie.onrender.com"
    }

    private static func discoverReleaseChannel(config: AppBundleRuntimeConfig?) -> String {
        if let configured = ProcessInfo.processInfo.environment["CALCIE_RELEASE_CHANNEL"],
           !configured.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return configured
        }
        if let configured = config?.release_channel?.trimmingCharacters(in: .whitespacesAndNewlines),
           !configured.isEmpty {
            return configured
        }
        return "alpha"
    }

    private static func describeAppBundle(config: AppBundleRuntimeConfig?, repoRoot: String) -> String {
        let buildConfiguration = config?.build_configuration ?? "unknown"
        let signingStyle = (config?.code_signing_style ?? "unknown").uppercased()
        let builtAt = config?.built_at ?? "unknown"
        let repoBacked = (config?.repo_backed ?? true) ? "repo-backed" : "bundled runtime"
        let channel = config?.release_channel ?? "alpha"
        return "Build: \(buildConfiguration) · signing \(signingStyle) · built \(builtAt) · \(repoBacked) · channel \(channel) · root \(repoRoot)"
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

    private static func releaseIsNewer(
        remoteVersion: String,
        remoteBuild: String,
        currentVersion: String,
        currentBuild: String
    ) -> Bool {
        let remoteParts = versionParts(remoteVersion)
        let currentParts = versionParts(currentVersion)
        for index in 0..<max(remoteParts.count, currentParts.count) {
            let remote = index < remoteParts.count ? remoteParts[index] : 0
            let current = index < currentParts.count ? currentParts[index] : 0
            if remote > current { return true }
            if remote < current { return false }
        }
        return (Int(remoteBuild) ?? 0) > (Int(currentBuild) ?? 0)
    }

    private static func versionParts(_ version: String) -> [Int] {
        version
            .split(separator: ".")
            .map { Int($0.filter { $0.isNumber }) ?? 0 }
    }

    private func appendChatMessage(role: String, text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        chatMessages.append(ChatMessage(role: role, text: trimmed, timestamp: Date()))
        if chatMessages.count > 30 {
            chatMessages.removeFirst(chatMessages.count - 30)
        }
    }

    private func replaceLastThinkingMessage(with text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        if let last = chatMessages.last, !last.isUser, last.text == "Thinking..." {
            chatMessages.removeLast()
        }
        appendChatMessage(role: "assistant", text: trimmed)
    }
}
