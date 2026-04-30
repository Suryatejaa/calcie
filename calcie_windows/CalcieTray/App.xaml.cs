using System.Windows;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using CalcieTray.Services;
using CalcieTray.ViewModels;
using System.Text.Json;

namespace CalcieTray;

public partial class App : System.Windows.Application
{
    private TrayController? _trayController;
    private MainWindow? _mainWindow;
    private PlayerWindowController? _playerWindowController;
    private SettingsWindowController? _settingsWindowController;
    private ShellViewModel? _viewModel;
    private HotkeyService? _hotkeyService;
    private DispatcherTimer? _playerCommandTimer;
    private string? _lastPlayerCommandId;
    private string? _playerCommandFilePath;

    protected override async void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        DispatcherUnhandledException += OnDispatcherUnhandledException;

        _viewModel = new ShellViewModel();
        _mainWindow = new MainWindow(_viewModel);
        if (TryLoadLogo() is { } logo)
        {
            _mainWindow.Icon = logo;
        }
        _playerWindowController = new PlayerWindowController();
        _settingsWindowController = new SettingsWindowController(_viewModel);
        _viewModel.ShowPlayerAction = () => _playerWindowController.ShowPlayer();
        _viewModel.ShowSettingsAction = () => _settingsWindowController.ShowSettings();
        _trayController = new TrayController(_mainWindow, _viewModel, _playerWindowController, _settingsWindowController);
        _viewModel.ShowNotificationAction = (title, message, icon) => _trayController?.ShowNotification(title, message, icon);
        _hotkeyService = new HotkeyService();
        if (_hotkeyService.Register())
        {
            _hotkeyService.PressStarted += async (_, _) =>
            {
                if (_viewModel is not null)
                {
                    await _viewModel.BeginPushToTalkAsync();
                }
            };

            _hotkeyService.PressEnded += async (_, _) =>
            {
                if (_viewModel is not null)
                {
                    await _viewModel.EndPushToTalkAsync();
                }
            };

            _hotkeyService.HotkeyPressed += async (_, _) =>
            {
                if (_viewModel is not null)
                {
                    await _viewModel.ToggleVoiceAsync();
                }
            };
        }

        _playerCommandFilePath = ResolvePlayerCommandFilePath();
        _playerCommandTimer = new DispatcherTimer
        {
            Interval = TimeSpan.FromMilliseconds(700)
        };
        _playerCommandTimer.Tick += OnPlayerCommandTimerTick;
        _playerCommandTimer.Start();

        _mainWindow.Hide();
        await _viewModel.InitializeAsync();
    }

    protected override void OnExit(ExitEventArgs e)
    {
        DispatcherUnhandledException -= OnDispatcherUnhandledException;
        if (_playerCommandTimer is not null)
        {
            _playerCommandTimer.Stop();
            _playerCommandTimer.Tick -= OnPlayerCommandTimerTick;
        }
        _hotkeyService?.Dispose();
        _trayController?.Dispose();
        _playerWindowController?.Dispose();
        _settingsWindowController?.Dispose();
        _viewModel?.Dispose();
        base.OnExit(e);
    }

    private void OnDispatcherUnhandledException(object sender, DispatcherUnhandledExceptionEventArgs e)
    {
        e.Handled = true;
        System.Windows.MessageBox.Show(
            $"CALCIE hit an unexpected Windows UI error.\n\n{e.Exception.Message}",
            "CALCIE",
            MessageBoxButton.OK,
            MessageBoxImage.Error);
    }

    private static BitmapFrame? TryLoadLogo()
    {
        try
        {
            return BitmapFrame.Create(new Uri("pack://application:,,,/Assets/calcie-logo.png", UriKind.Absolute));
        }
        catch
        {
            return null;
        }
    }

    private void OnPlayerCommandTimerTick(object? sender, EventArgs e)
    {
        if (_playerWindowController is null || string.IsNullOrWhiteSpace(_playerCommandFilePath))
        {
            return;
        }

        try
        {
            if (!File.Exists(_playerCommandFilePath))
            {
                return;
            }

            var raw = File.ReadAllText(_playerCommandFilePath);
            if (string.IsNullOrWhiteSpace(raw))
            {
                return;
            }

            var command = JsonSerializer.Deserialize<PlayerCommandPayload>(raw);
            if (command is null || string.IsNullOrWhiteSpace(command.RequestId))
            {
                return;
            }

            if (string.Equals(command.RequestId, _lastPlayerCommandId, StringComparison.Ordinal))
            {
                return;
            }

            _lastPlayerCommandId = command.RequestId;
            HandlePlayerCommand(command);
        }
        catch
        {
            // Keep the shell resilient if the file is mid-write or malformed.
        }
    }

    private void HandlePlayerCommand(PlayerCommandPayload command)
    {
        if (_playerWindowController is null)
        {
            return;
        }

        var action = (command.Action ?? string.Empty).Trim().ToLowerInvariant();
        switch (action)
        {
            case "load":
                _playerWindowController.LoadUrl(
                    string.IsNullOrWhiteSpace(command.Url) ? "https://music.youtube.com/" : command.Url!,
                    string.IsNullOrWhiteSpace(command.Title) ? "CALCIE Player" : command.Title!,
                    string.IsNullOrWhiteSpace(command.Subtitle) ? "Opening inside CALCIE Player." : command.Subtitle!
                );
                return;
            case "play":
                _playerWindowController.ResumePlayer();
                return;
            case "pause":
                _playerWindowController.PausePlayer();
                return;
            case "next":
                _playerWindowController.SkipNext();
                return;
            case "previous_track":
                _playerWindowController.PreviousTrack();
                return;
            case "restart_current":
                _playerWindowController.RestartCurrent();
                return;
            default:
                if (command.ShowPlayer)
                {
                    _playerWindowController.ShowPlayer();
                }
                return;
        }
    }

    private static string ResolvePlayerCommandFilePath()
    {
        var projectRoot = Environment.GetEnvironmentVariable("CALCIE_PROJECT_ROOT");
        if (!string.IsNullOrWhiteSpace(projectRoot))
        {
            return Path.Combine(projectRoot, ".calcie", "runtime", "media_player_command.json");
        }

        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            if (File.Exists(Path.Combine(current.FullName, "calcie.py")))
            {
                return Path.Combine(current.FullName, ".calcie", "runtime", "media_player_command.json");
            }

            current = current.Parent;
        }

        return Path.Combine(AppContext.BaseDirectory, ".calcie", "runtime", "media_player_command.json");
    }

    private sealed class PlayerCommandPayload
    {
        public string? Action { get; set; }
        public string? RequestId { get; set; }
        public string? Url { get; set; }
        public string? Title { get; set; }
        public string? Subtitle { get; set; }
        public bool ShowPlayer { get; set; }
    }
}
