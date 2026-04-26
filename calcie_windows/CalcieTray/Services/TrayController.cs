using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Forms;
using CalcieTray.ViewModels;
using Application = System.Windows.Application;
using DrawingColor = System.Drawing.Color;
using DrawingFontStyle = System.Drawing.FontStyle;
using DrawingPointF = System.Drawing.PointF;
using DrawingRectangle = System.Drawing.Rectangle;

namespace CalcieTray.Services;

public sealed class TrayController : IDisposable
{
    private readonly NotifyIcon _notifyIcon;
    private readonly MainWindow _window;
    private readonly ShellViewModel _viewModel;
    private readonly PlayerWindowController _playerWindowController;
    private readonly Icon _trayIcon;

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

        _trayIcon = BuildTrayIcon();
        _notifyIcon = new NotifyIcon
        {
            Text = "CALCIE",
            Icon = _trayIcon,
            Visible = true,
            ContextMenuStrip = menu
        };

        _notifyIcon.MouseClick += (_, e) =>
        {
            if (e.Button == MouseButtons.Left)
            {
                ToggleWindow(Control.MousePosition);
            }
        };
    }

    private void ToggleWindow(System.Drawing.Point? anchorPoint)
    {
        _window.ToggleTrayPopup(anchorPoint);
    }

    private void ShowWindow()
    {
        _window.ShowAsTrayPopup();
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
        _trayIcon.Dispose();
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

    private static Icon BuildTrayIcon()
    {
        using var bitmap = new Bitmap(64, 64);
        using var graphics = Graphics.FromImage(bitmap);
        graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
        graphics.Clear(DrawingColor.Transparent);

        using var tileBrush = new SolidBrush(DrawingColor.FromArgb(246, 16, 18, 22));
        using var ringPen = new Pen(DrawingColor.FromArgb(130, 119, 127, 140), 2f);
        var tileRect = new DrawingRectangle(7, 7, 50, 50);
        graphics.FillEllipse(tileBrush, tileRect);
        graphics.DrawEllipse(ringPen, tileRect);

        using var textBrush = new SolidBrush(DrawingColor.FromArgb(247, 248, 250));
        using var font = new Font("Segoe UI", 26, DrawingFontStyle.Bold, GraphicsUnit.Pixel);
        var size = graphics.MeasureString("C", font);
        var origin = new DrawingPointF(
            tileRect.Left + ((tileRect.Width - size.Width) / 2f),
            tileRect.Top + ((tileRect.Height - size.Height) / 2f) - 1f);
        graphics.DrawString("C", font, textBrush, origin);

        var iconHandle = bitmap.GetHicon();
        try
        {
            return (Icon)Icon.FromHandle(iconHandle).Clone();
        }
        finally
        {
            DestroyIcon(iconHandle);
        }
    }

    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    private static extern bool DestroyIcon(IntPtr handle);
}
