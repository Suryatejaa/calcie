using System.Text.Json.Serialization;

namespace CalcieTray.Models;

public sealed class RuntimeEvent
{
    public string Timestamp { get; set; } = "";
    public string Type { get; set; } = "";
    public string Summary { get; set; } = "";
    public string Severity { get; set; } = "";
    public string? Route { get; set; }
    public string? State { get; set; }

    public string MetaLine =>
        string.IsNullOrWhiteSpace(Route)
            ? $"{Timestamp} · {Type}"
            : $"{Timestamp} · {Type} · {Route}";
}

public sealed class RuntimeStatus
{
    [JsonPropertyName("state")]
    public string State { get; set; } = "offline";

    [JsonPropertyName("detail")]
    public string Detail { get; set; } = "";

    [JsonPropertyName("active_llm")]
    public string ActiveLlm { get; set; } = "";

    [JsonPropertyName("llm_mode")]
    public string LlmMode { get; set; } = "";

    [JsonPropertyName("tts_provider_mode")]
    public string TtsProviderMode { get; set; } = "";

    [JsonPropertyName("voice_available")]
    public bool VoiceAvailable { get; set; }

    [JsonPropertyName("tts_available")]
    public bool TtsAvailable { get; set; }

    [JsonPropertyName("is_speaking")]
    public bool IsSpeaking { get; set; }

    [JsonPropertyName("last_route")]
    public string LastRoute { get; set; } = "";

    [JsonPropertyName("last_user_command")]
    public string LastUserCommand { get; set; } = "";

    [JsonPropertyName("last_response")]
    public string LastResponse { get; set; } = "";

    [JsonPropertyName("vision_running")]
    public bool VisionRunning { get; set; }

    [JsonPropertyName("vision_status")]
    public string VisionStatus { get; set; } = "";

    [JsonPropertyName("current_monitor_goal")]
    public string CurrentMonitorGoal { get; set; } = "";

    [JsonPropertyName("permission_warnings")]
    public List<string> PermissionWarnings { get; set; } = new();

    [JsonPropertyName("skills")]
    public List<string> Skills { get; set; } = new();

    [JsonPropertyName("events_count")]
    public int EventsCount { get; set; }

    [JsonPropertyName("voice_session_active")]
    public bool? VoiceSessionActive { get; set; }
}

public sealed class CommandResponse
{
    public bool Ok { get; set; }
    public string Response { get; set; } = "";
    public string? Spoken { get; set; }
    public string? Route { get; set; }
    public string? State { get; set; }
}

public sealed class HealthResponse
{
    public bool Ok { get; set; }
    public string State { get; set; } = "offline";
}

public sealed class EventsEnvelope
{
    public bool Ok { get; set; }
    public List<RuntimeEvent> Events { get; set; } = new();
}

public sealed class UpdateManifestEnvelope
{
    [JsonPropertyName("ok")]
    public bool Ok { get; set; }

    [JsonPropertyName("update_available")]
    public bool UpdateAvailable { get; set; }

    [JsonPropertyName("release")]
    public UpdateRelease? Release { get; set; }
}

public sealed class UpdateRelease
{
    [JsonPropertyName("platform")]
    public string Platform { get; set; } = "";

    [JsonPropertyName("channel")]
    public string Channel { get; set; } = "";

    [JsonPropertyName("version")]
    public string Version { get; set; } = "";

    [JsonPropertyName("build")]
    public string Build { get; set; } = "";

    [JsonPropertyName("download_url")]
    public string DownloadUrl { get; set; } = "";

    [JsonPropertyName("sha256")]
    public string Sha256 { get; set; } = "";

    [JsonPropertyName("release_notes_url")]
    public string ReleaseNotesUrl { get; set; } = "";

    [JsonPropertyName("minimum_os")]
    public string MinimumOs { get; set; } = "";

    [JsonPropertyName("required")]
    public bool Required { get; set; }

    [JsonPropertyName("created_at")]
    public string CreatedAt { get; set; } = "";
}
