using CalcieTray.ViewModels;

namespace CalcieTray.Services;

public sealed class SettingsWindowController : IDisposable
{
    private readonly ShellViewModel _viewModel;
    private SettingsWindow? _settingsWindow;

    public SettingsWindowController(ShellViewModel viewModel)
    {
        _viewModel = viewModel;
    }

    public void ShowSettings()
    {
        EnsureWindow();
        _settingsWindow!.Show();
        _settingsWindow.Activate();
    }

    private void EnsureWindow()
    {
        if (_settingsWindow is not null)
        {
            return;
        }

        _settingsWindow = new SettingsWindow(_viewModel);
        _settingsWindow.Closed += (_, _) => _settingsWindow = null;
    }

    public void Dispose()
    {
        if (_settingsWindow is null)
        {
            return;
        }

        _settingsWindow.Close();
        _settingsWindow = null;
    }
}
