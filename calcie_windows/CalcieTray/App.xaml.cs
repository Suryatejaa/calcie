using System.Windows;
using CalcieTray.Services;
using CalcieTray.ViewModels;

namespace CalcieTray;

public partial class App : Application
{
    private TrayController? _trayController;
    private MainWindow? _mainWindow;
    private PlayerWindowController? _playerWindowController;
    private ShellViewModel? _viewModel;
    private HotkeyService? _hotkeyService;

    protected override async void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        _viewModel = new ShellViewModel();
        _mainWindow = new MainWindow(_viewModel);
        _playerWindowController = new PlayerWindowController();
        _viewModel.ShowPlayerAction = () => _playerWindowController.ShowPlayer();
        _trayController = new TrayController(_mainWindow, _viewModel, _playerWindowController);
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

        _mainWindow.Hide();
        await _viewModel.InitializeAsync();
    }

    protected override void OnExit(ExitEventArgs e)
    {
        _hotkeyService?.Dispose();
        _trayController?.Dispose();
        _playerWindowController?.Dispose();
        _viewModel?.Dispose();
        base.OnExit(e);
    }
}
