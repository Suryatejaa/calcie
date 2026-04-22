import Foundation

struct RuntimeEvent: Decodable, Identifiable {
    let timestamp: String
    let type: String
    let summary: String
    let severity: String
    let route: String?
    let state: String?

    var id: String { "\(timestamp)-\(type)-\(summary)" }
}

struct RuntimeStatus: Decodable {
    let state: String
    let detail: String
    let active_llm: String
    let llm_mode: String
    let tts_provider_mode: String
    let voice_available: Bool
    let tts_available: Bool
    let is_speaking: Bool
    let last_route: String
    let last_user_command: String
    let last_response: String
    let vision_running: Bool
    let vision_status: String
    let current_monitor_goal: String
    let permission_warnings: [String]
    let skills: [String]
    let events_count: Int
    let voice_session_active: Bool?
    let voice_cancel_requested: Bool?
    let runtime_instance_id: String?
    let runtime_pid: Int?
    let runtime_started_at: String?
    let runtime_project_root: String?
    let runtime_api_version: String?
    let profile_import: ProfileImportStatus?
}

struct CommandResponse: Decodable {
    let ok: Bool
    let response: String
    let spoken: String?
    let route: String?
    let state: String?
}

struct HealthResponse: Decodable {
    let ok: Bool
    let state: String
    let runtime_instance_id: String?
    let runtime_pid: Int?
    let runtime_started_at: String?
    let runtime_project_root: String?
    let runtime_api_version: String?
}

struct EventsEnvelope: Decodable {
    let ok: Bool
    let events: [RuntimeEvent]
}

struct ProfileImportStatus: Decodable {
    let ok: Bool?
    let has_profile: Bool
    let profile_file: String
    let has_chatgpt_import: Bool
    let imported_at: String
    let imported_chars: Int
    let import_prompt: String
}

struct ProfileImportResponse: Decodable {
    let ok: Bool
    let response: String
    let profile_file: String?
    let imported_at: String?
    let imported_chars: Int?
}

struct LocalAPIClient {
    let baseURL: URL

    init(baseURL: URL = URL(string: "http://127.0.0.1:8765")!) {
        self.baseURL = baseURL
    }

    func health() async throws -> HealthResponse {
        try await get("health", as: HealthResponse.self)
    }

    func status() async throws -> RuntimeStatus {
        try await get("status", as: RuntimeStatus.self)
    }

    func events(limit: Int = 20) async throws -> [RuntimeEvent] {
        var components = URLComponents(url: baseURL.appending(path: "events"), resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "limit", value: "\(limit)")]
        let envelope = try await get(components.url!, as: EventsEnvelope.self)
        return envelope.events
    }

    func command(_ text: String) async throws -> CommandResponse {
        try await post("command", body: ["text": text], as: CommandResponse.self)
    }

    func startVoice() async throws -> CommandResponse {
        try await post("voice/start", body: [:] as [String: String], as: CommandResponse.self)
    }

    func stopVoice() async throws -> CommandResponse {
        try await post("voice/stop", body: [:] as [String: String], as: CommandResponse.self)
    }

    func startVision(goal: String) async throws -> CommandResponse {
        try await post("vision/start", body: ["goal": goal], as: CommandResponse.self)
    }

    func stopVision() async throws -> CommandResponse {
        try await post("vision/stop", body: [:] as [String: String], as: CommandResponse.self)
    }

    func restartRuntime() async throws -> CommandResponse {
        try await post("runtime/restart", body: [:] as [String: String], as: CommandResponse.self)
    }

    func profileImportStatus() async throws -> ProfileImportStatus {
        try await get("profile/import-status", as: ProfileImportStatus.self)
    }

    func importChatGPTProfile(text: String) async throws -> ProfileImportResponse {
        try await post("profile/import-chatgpt", body: ["text": text], as: ProfileImportResponse.self)
    }

    private func get<T: Decodable>(_ path: String, as type: T.Type) async throws -> T {
        let url = baseURL.appending(path: path)
        return try await get(url, as: type)
    }

    private func get<T: Decodable>(_ url: URL, as type: T.Type) async throws -> T {
        let (data, response) = try await URLSession.shared.data(from: url)
        try validate(response)
        return try JSONDecoder().decode(T.self, from: data)
    }

    private func post<T: Decodable, Body: Encodable>(_ path: String, body: Body, as type: T.Type) async throws -> T {
        let url = baseURL.appending(path: path)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(body)
        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response)
        return try JSONDecoder().decode(T.self, from: data)
    }

    private func validate(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else {
            throw NSError(domain: "CalcieMenuBar", code: -1, userInfo: [NSLocalizedDescriptionKey: "Invalid response"])
        }
        guard (200...299).contains(http.statusCode) else {
            throw NSError(domain: "CalcieMenuBar", code: http.statusCode, userInfo: [NSLocalizedDescriptionKey: "Local API request failed with status \(http.statusCode)"])
        }
    }
}
