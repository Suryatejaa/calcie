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

    public void ShowAsTrayPopup()
    {
        PositionNearSystemTray();
        _lastTrayShowUtc = DateTime.UtcNow;
        Show();
        Activate();
        Focus();
    }

    public void ToggleTrayPopup()
    {
        if (IsVisible)
        {
            Hide();
            return;
        }

        ShowAsTrayPopup();
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

    private void PositionNearSystemTray()
    {
        var workArea = SystemParameters.WorkArea;
        Left = Math.Max(workArea.Left + 10, workArea.Right - Width - 8);
        Top = Math.Max(workArea.Top + 10, workArea.Bottom - Height - 6);
    }
}
