using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Diagnostics;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Windows;
using System.Windows.Input;
using System.Windows.Forms;
using CalcieTray.Models;
using CalcieTray.Services;

namespace CalcieTray.ViewModels;

public sealed class ShellViewModel : INotifyPropertyChanged, IDisposable
{
    private readonly LocalApiClient _client = new();
    private readonly RuntimeLauncher _runtimeLauncher = new();
    private readonly CancellationTokenSource _shutdown = new();
    private readonly RelayCommand _submitCommand;
    private readonly RelayCommand _submitVisionCommand;
    private readonly string _cloudBaseUrl;
    private readonly string _releaseChannel;
    private string _runtimeState = "starting";
    private string _runtimeDetail = "Connecting to local CALCIE runtime...";
    private string _pendingCommand = "";
    private string _lastResponse = "Waiting for CALCIE...";
    private bool _voiceSessionActive;
    private string _updateStatusMessage = "Update check has not run yet.";
    private bool _updateAvailable;
    private string _updateVersion = "";
    private string _updateBuild = "";
    private string _updateDownloadUrl = "";
    private string _updateReleaseNotesUrl = "";
    private bool _updateRequired;
    private string _lastNotifiedResponse = "";
    private string _lastNotifiedUpdateKey = "";

    public ShellViewModel()
    {
        _cloudBaseUrl = DiscoverCloudBaseUrl();
        _releaseChannel = DiscoverReleaseChannel();
        _submitCommand = new RelayCommand(async _ => await SubmitAsync(), _ => !string.IsNullOrWhiteSpace(PendingCommand));
        _submitVisionCommand = new RelayCommand(async _ => await SubmitVisionAsync(), _ => !string.IsNullOrWhiteSpace(PendingCommand));
        RefreshCommand = new RelayCommand(async _ => await RefreshAsync());
        RestartRuntimeCommand = new RelayCommand(async _ => await RestartRuntimeAsync());
        RefreshUpdateCommand = new RelayCommand(async _ => await RefreshUpdateStatusAsync());
        DownloadUpdateCommand = new RelayCommand(_ => OpenUrl(UpdateDownloadUrl), _ => !string.IsNullOrWhiteSpace(UpdateDownloadUrl));
        OpenReleaseNotesCommand = new RelayCommand(_ => OpenUrl(UpdateReleaseNotesUrl), _ => !string.IsNullOrWhiteSpace(UpdateReleaseNotesUrl));
        OpenPlayerCommand = new RelayCommand(_ => ShowPlayerAction?.Invoke());
        StartVoiceCommand = new RelayCommand(async _ => await StartVoiceAsync());
        StopVoiceCommand = new RelayCommand(async _ => await StopVoiceAsync());
    }

    public ObservableCollection<RuntimeEvent> Events { get; } = new();

    public ICommand RefreshCommand { get; }
    public ICommand RestartRuntimeCommand { get; }
    public ICommand RefreshUpdateCommand { get; }
    public ICommand DownloadUpdateCommand { get; }
    public ICommand OpenReleaseNotesCommand { get; }
    public ICommand OpenPlayerCommand { get; }
    public ICommand StartVoiceCommand { get; }
    public ICommand StopVoiceCommand { get; }
    public ICommand SubmitCommand => _submitCommand;
    public ICommand SubmitVisionCommand => _submitVisionCommand;

    public Action? ShowPlayerAction { get; set; }
    public Action<string, string, ToolTipIcon>? ShowNotificationAction { get; set; }

    public string RuntimeState
    {
        get => _runtimeState;
        private set
        {
            if (SetField(ref _runtimeState, value))
            {
                OnPropertyChanged(nameof(RuntimeStateLabel));
            }
        }
    }

    public string RuntimeStateLabel => $"State: {RuntimeState}";

    public string RuntimeDetail
    {
        get => _runtimeDetail;
        private set => SetField(ref _runtimeDetail, value);
    }

    public string PendingCommand
    {
        get => _pendingCommand;
        set
        {
            if (SetField(ref _pendingCommand, value))
            {
                _submitCommand.RaiseCanExecuteChanged();
                _submitVisionCommand.RaiseCanExecuteChanged();
            }
        }
    }

    public string LastResponse
    {
        get => _lastResponse;
        private set => SetField(ref _lastResponse, value);
    }

    public bool VoiceSessionActive
    {
        get => _voiceSessionActive;
        private set => SetField(ref _voiceSessionActive, value);
    }

    public string UpdateStatusMessage
    {
        get => _updateStatusMessage;
        private set => SetField(ref _updateStatusMessage, value);
    }

    public bool UpdateAvailable
    {
        get => _updateAvailable;
        private set => SetField(ref _updateAvailable, value);
    }

    public string UpdateVersion
    {
        get => _updateVersion;
        private set => SetField(ref _updateVersion, value);
    }

    public string UpdateBuild
    {
        get => _updateBuild;
        private set => SetField(ref _updateBuild, value);
    }

    public string UpdateDownloadUrl
    {
        get => _updateDownloadUrl;
        private set
        {
            if (SetField(ref _updateDownloadUrl, value))
            {
                if (DownloadUpdateCommand is RelayCommand relay)
                {
                    relay.RaiseCanExecuteChanged();
                }
            }
        }
    }

    public string UpdateReleaseNotesUrl
    {
        get => _updateReleaseNotesUrl;
        private set
        {
            if (SetField(ref _updateReleaseNotesUrl, value))
            {
                if (OpenReleaseNotesCommand is RelayCommand relay)
                {
                    relay.RaiseCanExecuteChanged();
                }
            }
        }
    }

    public bool UpdateRequired
    {
        get => _updateRequired;
        private set => SetField(ref _updateRequired, value);
    }

    public async Task InitializeAsync()
    {
        await RefreshAsync();
        await RefreshUpdateStatusAsync();
        _ = Task.Run(PollLoopAsync);
    }

    public async Task RefreshAsync()
    {
        try
        {
            var status = await _client.StatusAsync(_shutdown.Token);
            if (status is null)
            {
                ApplyOfflineState("Runtime returned no status payload.");
                return;
            }

            RuntimeState = status.State;
            RuntimeDetail = string.IsNullOrWhiteSpace(status.Detail)
                ? $"LLM: {status.ActiveLlm} · TTS: {status.TtsProviderMode}"
                : status.Detail;
            VoiceSessionActive = status.VoiceSessionActive ?? false;

            if (!string.IsNullOrWhiteSpace(status.LastResponse))
            {
                LastResponse = status.LastResponse;
            }

            await RefreshEventsAsync();
        }
        catch (Exception ex)
        {
            ApplyOfflineState(ex.Message);
            TryLaunchRuntime();
        }
    }

    public async Task StartVoiceAsync()
    {
        await ExecuteResponseAsync(() => _client.StartVoiceAsync(_shutdown.Token), "Voice capture started.");
    }

    public async Task StopVoiceAsync()
    {
        await ExecuteResponseAsync(() => _client.StopVoiceAsync(_shutdown.Token), "Voice stop requested.");
    }

    public async Task ToggleVoiceAsync()
    {
        if (VoiceSessionActive)
        {
            await StopVoiceAsync();
        }
        else
        {
            await StartVoiceAsync();
        }
    }

    public async Task BeginPushToTalkAsync()
    {
        if (!VoiceSessionActive)
        {
            await StartVoiceAsync();
        }
    }

    public async Task EndPushToTalkAsync()
    {
        if (VoiceSessionActive)
        {
            await StopVoiceAsync();
        }
    }

    public async Task RestartRuntimeAsync()
    {
        await ExecuteResponseAsync(
            () => _client.RestartRuntimeAsync(_shutdown.Token),
            "Runtime restart requested."
        );
        try
        {
            await Task.Delay(1200, _shutdown.Token);
        }
        catch (OperationCanceledException)
        {
            return;
        }
        await RefreshAsync();
    }

    public async Task RefreshUpdateStatusAsync()
    {
        var baseUrl = _cloudBaseUrl.Trim();
        if (string.IsNullOrWhiteSpace(baseUrl))
        {
            UpdateAvailable = false;
            UpdateStatusMessage = "Update check is not configured. Set CALCIE_CLOUD_BASE_URL or CALCIE_SYNC_BASE_URL.";
            return;
        }

        try
        {
            var envelope = await _client.LatestReleaseAsync(baseUrl, "windows", _releaseChannel, _shutdown.Token);
            ApplyUpdateManifest(envelope);
        }
        catch (Exception ex)
        {
            UpdateAvailable = false;
            UpdateStatusMessage = $"Update check failed: {ex.Message}";
        }
    }

    public async Task SubmitAsync()
    {
        var text = PendingCommand.Trim();
        if (string.IsNullOrWhiteSpace(text))
        {
            return;
        }

        PendingCommand = "";
        await ExecuteResponseAsync(() => _client.CommandAsync(text, _shutdown.Token), $"Submitted: {text}");
    }

    public async Task SubmitVisionAsync()
    {
        var text = PendingCommand.Trim();
        if (string.IsNullOrWhiteSpace(text))
        {
            return;
        }

        PendingCommand = "";
        await ExecuteResponseAsync(() => _client.CommandAsync($"vision once {text}", _shutdown.Token), $"Vision requested: {text}");
    }

    private async Task ExecuteResponseAsync(Func<Task<CommandResponse?>> action, string fallbackMessage)
    {
        try
        {
            var response = await action();
            if (response is null)
            {
                LastResponse = fallbackMessage;
            }
            else
            {
                RuntimeState = response.State ?? RuntimeState;
                LastResponse = string.IsNullOrWhiteSpace(response.Response) ? fallbackMessage : response.Response;
            }

            NotifyAssistantResponse(LastResponse);

            await RefreshAsync();
        }
        catch (Exception ex)
        {
            RuntimeState = "error";
            RuntimeDetail = "Command execution failed";
            LastResponse = ex.Message;
            ShowNotificationAction?.Invoke("CALCIE Error", ex.Message, ToolTipIcon.Error);
        }
    }

    private async Task RefreshEventsAsync()
    {
        var events = await _client.EventsAsync(cancellationToken: _shutdown.Token);

        Application.Current.Dispatcher.Invoke(() =>
        {
            Events.Clear();
            foreach (var item in events)
            {
                Events.Add(item);
            }
        });
    }

    private async Task PollLoopAsync()
    {
        var timer = new PeriodicTimer(TimeSpan.FromSeconds(5));
        try
        {
            while (await timer.WaitForNextTickAsync(_shutdown.Token))
            {
                await RefreshAsync();
            }
        }
        catch (OperationCanceledException)
        {
        }
        finally
        {
            timer.Dispose();
        }
    }

    private void ApplyOfflineState(string reason)
    {
        RuntimeState = "offline";
        RuntimeDetail = $"Local runtime unavailable: {reason}";
    }

    private void TryLaunchRuntime()
    {
        var launchMessage = _runtimeLauncher.EnsureRunning();
        if (!string.IsNullOrWhiteSpace(launchMessage))
        {
            RuntimeDetail = launchMessage;
        }
    }

    private void ApplyUpdateManifest(UpdateManifestEnvelope? envelope)
    {
        if (envelope is null || !envelope.Ok)
        {
            UpdateAvailable = false;
            UpdateStatusMessage = "Update service returned an error.";
            return;
        }

        if (!envelope.UpdateAvailable || envelope.Release is null)
        {
            UpdateAvailable = false;
            UpdateStatusMessage = $"CALCIE is up to date on {_releaseChannel}.";
            return;
        }

        var release = envelope.Release;
        var currentVersion = Assembly.GetExecutingAssembly().GetName().Version?.ToString(3) ?? "0.0.0";
        var currentBuild = Assembly.GetExecutingAssembly().GetName().Version?.Build.ToString() ?? "0";

        UpdateVersion = release.Version;
        UpdateBuild = release.Build;
        UpdateDownloadUrl = release.DownloadUrl;
        UpdateReleaseNotesUrl = release.ReleaseNotesUrl;
        UpdateRequired = release.Required;
        UpdateAvailable = ReleaseIsNewer(release.Version, release.Build, currentVersion, currentBuild);

        if (UpdateAvailable)
        {
            var requiredText = release.Required ? " Required update." : "";
            UpdateStatusMessage = $"CALCIE {release.Version} build {release.Build} is available on {release.Channel}.{requiredText}";
            NotifyUpdateIfNeeded(release);
        }
        else
        {
            UpdateStatusMessage = $"No newer update on {release.Channel}. Current: {currentVersion} build {currentBuild}.";
        }
    }

    private static bool ReleaseIsNewer(string remoteVersion, string remoteBuild, string currentVersion, string currentBuild)
    {
        var remoteParts = VersionParts(remoteVersion);
        var currentParts = VersionParts(currentVersion);

        for (var index = 0; index < Math.Max(remoteParts.Count, currentParts.Count); index++)
        {
            var remote = index < remoteParts.Count ? remoteParts[index] : 0;
            var current = index < currentParts.Count ? currentParts[index] : 0;
            if (remote > current) return true;
            if (remote < current) return false;
        }

        return (int.TryParse(remoteBuild, out var remoteInt) ? remoteInt : 0) >
               (int.TryParse(currentBuild, out var currentInt) ? currentInt : 0);
    }

    private static List<int> VersionParts(string version) =>
        version
            .Split('.', StringSplitOptions.RemoveEmptyEntries)
            .Select(part => int.TryParse(new string(part.Where(char.IsDigit).ToArray()), out var number) ? number : 0)
            .ToList();

    private static void OpenUrl(string url)
    {
        if (string.IsNullOrWhiteSpace(url))
        {
            return;
        }

        var process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = url,
                UseShellExecute = true
            }
        };

        process.Start();
    }

    private void NotifyAssistantResponse(string text)
    {
        var trimmed = text.Trim();
        if (string.IsNullOrWhiteSpace(trimmed) || trimmed == _lastNotifiedResponse)
        {
            return;
        }

        _lastNotifiedResponse = trimmed;
        ShowNotificationAction?.Invoke("CALCIE", trimmed, ToolTipIcon.Info);
    }

    private void NotifyUpdateIfNeeded(UpdateRelease release)
    {
        var key = $"{release.Version}:{release.Build}:{release.Channel}";
        if (key == _lastNotifiedUpdateKey)
        {
            return;
        }

        _lastNotifiedUpdateKey = key;
        var message = $"CALCIE {release.Version} build {release.Build} is ready on {release.Channel}.";
        ShowNotificationAction?.Invoke("Update Available", message, ToolTipIcon.Info);
    }

    private static string DiscoverCloudBaseUrl()
    {
        var explicitCloud = Environment.GetEnvironmentVariable("CALCIE_CLOUD_BASE_URL");
        if (!string.IsNullOrWhiteSpace(explicitCloud))
        {
            return explicitCloud;
        }

        var syncBase = Environment.GetEnvironmentVariable("CALCIE_SYNC_BASE_URL");
        if (!string.IsNullOrWhiteSpace(syncBase))
        {
            return syncBase;
        }

        return "https://calcie.onrender.com";
    }

    private static string DiscoverReleaseChannel()
    {
        var explicitChannel = Environment.GetEnvironmentVariable("CALCIE_RELEASE_CHANNEL");
        return string.IsNullOrWhiteSpace(explicitChannel) ? "alpha" : explicitChannel.Trim();
    }

    private bool SetField<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value))
        {
            return false;
        }

        field = value;
        OnPropertyChanged(propertyName);
        return true;
    }

    private void OnPropertyChanged([CallerMemberName] string? propertyName = null)
    {
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    }

    public void Dispose()
    {
        _shutdown.Cancel();
        _runtimeLauncher.Dispose();
        _shutdown.Dispose();
    }

    public event PropertyChangedEventHandler? PropertyChanged;
}
