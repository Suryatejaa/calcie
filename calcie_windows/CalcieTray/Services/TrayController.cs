using System.Drawing;
using System.Windows;
using System.Windows.Forms;
using CalcieTray.ViewModels;
using Application = System.Windows.Application;

namespace CalcieTray.Services;

public sealed class TrayController : IDisposable
{
    private readonly NotifyIcon _notifyIcon;
    private readonly MainWindow _window;
    private readonly ShellViewModel _viewModel;
    private readonly PlayerWindowController _playerWindowController;

    public TrayController(MainWindow window, ShellViewModel viewModel, PlayerWindowController playerWindowController)
    {
        _window = window;
        _viewModel = viewModel;
        _playerWindowController = playerWindowController;

        var menu = new ContextMenuStrip();
        menu.Items.Add("Open CALCIE", null, (_, _) => ShowWindow());
        menu.Items.Add("Open Player", null, (_, _) => _playerWindowController.ShowPlayer());
        menu.Items.Add("Refresh", null, async (_, _) => await _viewModel.RefreshAsync());
        menu.Items.Add("Restart Runtime", null, async (_, _) => await _viewModel.RestartRuntimeAsync());
        menu.Items.Add("Quit", null, (_, _) => Quit());

        _notifyIcon = new NotifyIcon
        {
            Text = "CALCIE",
            Icon = SystemIcons.Application,
            Visible = true,
            ContextMenuStrip = menu
        };

        _notifyIcon.DoubleClick += (_, _) => ShowWindow();
    }

    private void ShowWindow()
    {
        _window.Show();
        if (_window.WindowState == WindowState.Minimized)
        {
            _window.WindowState = WindowState.Normal;
        }

        _window.Activate();
        _window.Topmost = true;
        _window.Topmost = false;
        _window.Focus();
    }

    private void Quit()
    {
        _notifyIcon.Visible = false;
        _window.AllowExit = true;
        _window.Close();
        Application.Current.Shutdown();
    }

    public void Dispose()
    {
        _notifyIcon.Visible = false;
        _notifyIcon.Dispose();
    }

    public void ShowNotification(string title, string message, ToolTipIcon icon = ToolTipIcon.Info)
    {
        var safeTitle = string.IsNullOrWhiteSpace(title) ? "CALCIE" : title;
        var safeMessage = string.IsNullOrWhiteSpace(message) ? "CALCIE has an update." : message;
        if (safeMessage.Length > 220)
        {
            safeMessage = safeMessage[..217] + "...";
        }

        _notifyIcon.BalloonTipTitle = safeTitle;
        _notifyIcon.BalloonTipText = safeMessage;
        _notifyIcon.BalloonTipIcon = icon;
        _notifyIcon.ShowBalloonTip(4000);
    }
}
