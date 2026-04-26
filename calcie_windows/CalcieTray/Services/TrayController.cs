using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Runtime.InteropServices;
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
    private readonly SettingsWindowController _settingsWindowController;
    private readonly Icon _trayIcon;

    public TrayController(MainWindow window, ShellViewModel viewModel, PlayerWindowController playerWindowController, SettingsWindowController settingsWindowController)
    {
        _window = window;
        _viewModel = viewModel;
        _playerWindowController = playerWindowController;
        _settingsWindowController = settingsWindowController;

        var menu = new ContextMenuStrip();
        menu.Items.Add("Open CALCIE", null, (_, _) => ShowWindow());
        menu.Items.Add("Settings", null, (_, _) => _settingsWindowController.ShowSettings());
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
        using Stream? stream = typeof(TrayController).Assembly.GetManifestResourceStream("CalcieTray.Assets.calcie-logo.png");
        using var sourceBitmap = stream is not null ? new Bitmap(stream) : new Bitmap(500, 500);
        using var iconBitmap = new Bitmap(64, 64);
        using (var graphics = Graphics.FromImage(iconBitmap))
        {
            graphics.SmoothingMode = SmoothingMode.AntiAlias;
            graphics.InterpolationMode = InterpolationMode.HighQualityBicubic;
            graphics.PixelOffsetMode = PixelOffsetMode.HighQuality;
            graphics.Clear(Color.Transparent);

            using var shadowBrush = new SolidBrush(Color.FromArgb(70, 0, 0, 0));
            using var cardBrush = new SolidBrush(Color.FromArgb(255, 18, 18, 20));
            using var cardBorder = new Pen(Color.FromArgb(255, 52, 52, 58), 2f);

            var shadowRect = new RectangleF(6f, 8f, 52f, 52f);
            var cardRect = new RectangleF(4f, 6f, 52f, 52f);

            using var shadowPath = CreateRoundedRectangle(shadowRect, 15f);
            using var cardPath = CreateRoundedRectangle(cardRect, 15f);
            graphics.FillPath(shadowBrush, shadowPath);
            graphics.FillPath(cardBrush, cardPath);
            graphics.DrawPath(cardBorder, cardPath);

            var logoRect = new RectangleF(12f, 14f, 36f, 36f);
            graphics.DrawImage(sourceBitmap, logoRect);
        }

        var iconHandle = iconBitmap.GetHicon();
        try
        {
            return (Icon)Icon.FromHandle(iconHandle).Clone();
        }
        finally
        {
            DestroyIcon(iconHandle);
        }
    }

    private static GraphicsPath CreateRoundedRectangle(RectangleF rect, float radius)
    {
        var diameter = radius * 2f;
        var path = new GraphicsPath();

        path.AddArc(rect.X, rect.Y, diameter, diameter, 180, 90);
        path.AddArc(rect.Right - diameter, rect.Y, diameter, diameter, 270, 90);
        path.AddArc(rect.Right - diameter, rect.Bottom - diameter, diameter, diameter, 0, 90);
        path.AddArc(rect.X, rect.Bottom - diameter, diameter, diameter, 90, 90);
        path.CloseFigure();

        return path;
    }

    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    private static extern bool DestroyIcon(IntPtr handle);
}
