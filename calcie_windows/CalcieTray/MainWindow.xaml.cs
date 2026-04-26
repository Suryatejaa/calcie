using System.ComponentModel;
using System.Windows;
using CalcieTray.ViewModels;

namespace CalcieTray;

public partial class MainWindow : Window
{
    public bool AllowExit { get; set; }

    public MainWindow(ShellViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
    }

    public void ShowAsTrayPopup()
    {
        PositionNearSystemTray();
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
        Left = Math.Max(workArea.Left + 12, workArea.Right - Width - 12);
        Top = Math.Max(workArea.Top + 12, workArea.Bottom - Height - 12);
    }
}
