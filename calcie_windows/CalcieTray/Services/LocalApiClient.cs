using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;
using CalcieTray.Models;

namespace CalcieTray.Services;

public sealed class LocalApiClient
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
    };

    private readonly HttpClient _statusClient;
    private readonly HttpClient _commandClient;

    public LocalApiClient(string baseUrl = "http://127.0.0.1:8765")
    {
        _statusClient = new HttpClient
        {
            BaseAddress = new Uri(baseUrl),
            Timeout = TimeSpan.FromSeconds(8)
        };

        _commandClient = new HttpClient
        {
            BaseAddress = new Uri(baseUrl),
            Timeout = TimeSpan.FromSeconds(30)
        };
    }

    public Task<HealthResponse?> HealthAsync(CancellationToken cancellationToken = default) =>
        GetAsync<HealthResponse>("health", cancellationToken);

    public Task<RuntimeStatus?> StatusAsync(CancellationToken cancellationToken = default) =>
        GetAsync<RuntimeStatus>("status", cancellationToken);

    public async Task<IReadOnlyList<RuntimeEvent>> EventsAsync(int limit = 12, CancellationToken cancellationToken = default)
    {
        var envelope = await GetAsync<EventsEnvelope>($"events?limit={limit}", cancellationToken);
        return envelope?.Events ?? (IReadOnlyList<RuntimeEvent>)Array.Empty<RuntimeEvent>();
    }

    public Task<CommandResponse?> CommandAsync(string text, CancellationToken cancellationToken = default) =>
        PostAsync<CommandResponse>("command", new { text }, cancellationToken);

    public Task<CommandResponse?> StartVoiceAsync(CancellationToken cancellationToken = default) =>
        PostAsync<CommandResponse>("voice/start", new { }, cancellationToken);

    public Task<CommandResponse?> StopVoiceAsync(CancellationToken cancellationToken = default) =>
        PostAsync<CommandResponse>("voice/stop", new { }, cancellationToken);

    public Task<CommandResponse?> StartVisionAsync(string goal, CancellationToken cancellationToken = default) =>
        PostAsync<CommandResponse>("vision/start", new { goal }, cancellationToken);

    public Task<CommandResponse?> StopVisionAsync(CancellationToken cancellationToken = default) =>
        PostAsync<CommandResponse>("vision/stop", new { }, cancellationToken);

    public Task<CommandResponse?> RestartRuntimeAsync(CancellationToken cancellationToken = default) =>
        PostAsync<CommandResponse>("runtime/restart", new { }, cancellationToken);

    public Task<ProfileImportStatus?> ProfileImportStatusAsync(CancellationToken cancellationToken = default) =>
        GetAsync<ProfileImportStatus>("profile/import-status", cancellationToken);

    public Task<ProfileImportResponse?> ImportChatGptProfileAsync(string text, CancellationToken cancellationToken = default) =>
        PostAsync<ProfileImportResponse>("profile/import-chatgpt", new { text }, cancellationToken);

    public async Task<UpdateManifestEnvelope?> LatestReleaseAsync(string baseUrl, string platform, string channel, CancellationToken cancellationToken = default)
    {
        using var httpClient = new HttpClient
        {
            BaseAddress = new Uri(baseUrl),
            Timeout = TimeSpan.FromSeconds(10)
        };

        var url = $"updates/latest?platform={Uri.EscapeDataString(platform)}&channel={Uri.EscapeDataString(channel)}";
        using var response = await httpClient.GetAsync(url, cancellationToken);
        response.EnsureSuccessStatusCode();
        await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
        return await JsonSerializer.DeserializeAsync<UpdateManifestEnvelope>(stream, JsonOptions, cancellationToken);
    }

    private async Task<T?> GetAsync<T>(string path, CancellationToken cancellationToken)
    {
        using var response = await _statusClient.GetAsync(path, cancellationToken);
        response.EnsureSuccessStatusCode();
        await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
        return await JsonSerializer.DeserializeAsync<T>(stream, JsonOptions, cancellationToken);
    }

    private async Task<T?> PostAsync<T>(string path, object payload, CancellationToken cancellationToken)
    {
        using var response = await _commandClient.PostAsJsonAsync(path, payload, JsonOptions, cancellationToken);
        response.EnsureSuccessStatusCode();
        await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
        return await JsonSerializer.DeserializeAsync<T>(stream, JsonOptions, cancellationToken);
    }
}
