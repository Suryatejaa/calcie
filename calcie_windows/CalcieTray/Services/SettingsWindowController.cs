using System.ComponentModel;
using System.Windows;
using System.Windows.Threading;
using CalcieTray.ViewModels;

namespace CalcieTray.Services;

public sealed class SettingsWindowController : IDisposable
{
    private readonly ShellViewModel _viewModel;
    private SettingsWindow? _settingsWindow;
    private bool _opening;

    public SettingsWindowController(ShellViewModel viewModel)
    {
        _viewModel = viewModel;
    }

    public void ShowSettings()
    {
        if (_opening)
        {
            return;
        }

        _opening = true;
        System.Windows.Application.Current.Dispatcher.BeginInvoke(DispatcherPriority.ApplicationIdle, new Action(() =>
        {
            try
            {
                EnsureWindow();
                if (_settingsWindow is null)
                {
                    return;
                }

                if (_settingsWindow.WindowState == WindowState.Minimized)
                {
                    _settingsWindow.WindowState = WindowState.Normal;
                }

                if (!_settingsWindow.IsVisible)
                {
                    _settingsWindow.Show();
                }

                _settingsWindow.Topmost = true;
                _settingsWindow.Activate();
                _settingsWindow.Focus();
                _settingsWindow.Topmost = false;
            }
            catch (Exception ex)
            {
                System.Windows.MessageBox.Show(
                    $"CALCIE could not open Settings.\n\n{ex.Message}",
                    "CALCIE",
                    MessageBoxButton.OK,
                    MessageBoxImage.Error);
            }
            finally
            {
                _opening = false;
            }
        }));
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
