using System.ComponentModel;
using System.Windows;
using CalcieTray.ViewModels;

namespace CalcieTray;

public partial class MainWindow : Window
{
    private DateTime _lastTrayShowUtc = DateTime.MinValue;

    public bool AllowExit { get; set; }

    public MainWindow(ShellViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
    }

    private void PendingCommandTextBox_OnPreviewKeyDown(object sender, System.Windows.Input.KeyEventArgs e)
    {
        if (e.Key != System.Windows.Input.Key.Enter)
        {
            return;
        }

        e.Handled = true;

        if (DataContext is not ShellViewModel viewModel)
        {
            return;
        }

        if (viewModel.SubmitCommand.CanExecute(null))
        {
            viewModel.SubmitCommand.Execute(null);
        }
    }

    public void ShowAsTrayPopup()
    {
        PositionNearTrayPoint(null);
        _lastTrayShowUtc = DateTime.UtcNow;
        Show();
        Activate();
        Focus();
    }

    public void ToggleTrayPopup(System.Drawing.Point? trayPoint = null)
    {
        if (IsVisible)
        {
            Hide();
            return;
        }

        PositionNearTrayPoint(trayPoint);
        _lastTrayShowUtc = DateTime.UtcNow;
        Show();
        Activate();
        Focus();
    }

    protected override void OnDeactivated(EventArgs e)
    {
        base.OnDeactivated(e);

        // When the popup is opened from the tray, Windows can briefly report a
        // deactivation caused by the tray click itself. Without a short grace
        // period, the panel appears to do nothing on single-click because it
        // opens and hides immediately.
        if ((DateTime.UtcNow - _lastTrayShowUtc).TotalMilliseconds < 350)
        {
            return;
        }

        if (!AllowExit && IsVisible)
        {
            Hide();
        }
    }

    protected override void OnClosing(CancelEventArgs e)
    {
        if (AllowExit)
        {
            base.OnClosing(e);
            return;
        }

        e.Cancel = true;
        Hide();
    }

    private void PositionNearTrayPoint(System.Drawing.Point? trayPoint)
    {
        var workArea = SystemParameters.WorkArea;
        if (trayPoint is { } point)
        {
            Left = Math.Max(workArea.Left + 8, Math.Min(workArea.Right - Width - 4, point.X - Width + 18));
            Top = Math.Max(workArea.Top + 8, Math.Min(workArea.Bottom - Height - 2, point.Y - Height - 6));
            return;
        }

        Left = Math.Max(workArea.Left + 8, workArea.Right - Width - 4);
        Top = Math.Max(workArea.Top + 8, workArea.Bottom - Height - 2);
    }
}
