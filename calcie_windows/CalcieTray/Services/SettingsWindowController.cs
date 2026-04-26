using System.ComponentModel;
using System.Windows;
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
        Application.Current.Dispatcher.Invoke(() =>
        {
            EnsureWindow();
            if (_settingsWindow is null)
            {
                return;
            }

            if (!_settingsWindow.IsVisible)
            {
                _settingsWindow.Show();
            }

            if (_settingsWindow.WindowState == WindowState.Minimized)
            {
                _settingsWindow.WindowState = WindowState.Normal;
            }

            _settingsWindow.Activate();
            _settingsWindow.Focus();
        });
    }

    private void EnsureWindow()
    {
        if (_settingsWindow is not null)
        {
            return;
        }

        _settingsWindow = new SettingsWindow(_viewModel);
        _settingsWindow.Closing += OnWindowClosing;
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

    private void OnWindowClosing(object? sender, CancelEventArgs e)
    {
        if (_settingsWindow is null)
        {
            return;
        }

        e.Cancel = true;
        _settingsWindow.Hide();
    }
}
