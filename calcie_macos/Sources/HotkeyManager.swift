import AppKit
import Foundation

@MainActor
final class HotkeyManager {
    static let shared = HotkeyManager()

    var onHoldStart: (() -> Void)?
    var onHoldEnd: (() -> Void)?

    private var globalMonitor: Any?
    private var localMonitor: Any?
    private var isRightOptionHeld = false

    private let rightOptionKeyCode: UInt16 = 61

    private init() {}

    func registerDefaultHotkey() {
        unregister()

        globalMonitor = NSEvent.addGlobalMonitorForEvents(matching: .flagsChanged) { [weak self] event in
            Task { @MainActor in
                self?.handleFlagsChanged(event)
            }
        }

        localMonitor = NSEvent.addLocalMonitorForEvents(matching: .flagsChanged) { [weak self] event in
            self?.handleFlagsChanged(event)
            return event
        }
    }

    func unregister() {
        if let globalMonitor {
            NSEvent.removeMonitor(globalMonitor)
            self.globalMonitor = nil
        }
        if let localMonitor {
            NSEvent.removeMonitor(localMonitor)
            self.localMonitor = nil
        }
        isRightOptionHeld = false
    }

    private func handleFlagsChanged(_ event: NSEvent) {
        guard event.keyCode == rightOptionKeyCode else { return }
        let currentlyHeld = event.modifierFlags.contains(.option)

        if currentlyHeld && !isRightOptionHeld {
            isRightOptionHeld = true
            onHoldStart?()
            return
        }

        if !currentlyHeld && isRightOptionHeld {
            isRightOptionHeld = false
            onHoldEnd?()
        }
    }
}
