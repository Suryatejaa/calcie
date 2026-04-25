using System.ComponentModel;
using System.Windows;

namespace CalcieTray;

public partial class PlayerWindow : Window
{
    public bool AllowExit { get; set; }

    public PlayerWindow()
    {
        InitializeComponent();
    }

    public void ShowPlayer()
    {
        Show();
        if (WindowState == WindowState.Minimized)
        {
            WindowState = WindowState.Normal;
        }

        Activate();
        Topmost = true;
        Topmost = false;
        Focus();
    }

    public void LoadUrl(string url, string title, string subtitle)
    {
        Title = title;
        StateText.Text = "Loading";
        SubtitleText.Text = subtitle;
        Browser.Navigate(url);
        ShowPlayer();
    }

    private void Reload_Click(object sender, RoutedEventArgs e)
    {
        StateText.Text = "Loading";
        Browser.Refresh();
    }

    private void YouTube_Click(object sender, RoutedEventArgs e)
    {
        LoadUrl("https://www.youtube.com/", "CALCIE Player", "Opening YouTube in the CALCIE-owned player surface.");
    }

    private void YouTubeMusic_Click(object sender, RoutedEventArgs e)
    {
        LoadUrl("https://music.youtube.com/", "CALCIE Player", "Opening YouTube Music in the CALCIE-owned player surface.");
    }

    protected override void OnContentRendered(EventArgs e)
    {
        base.OnContentRendered(e);
        if (Browser.Source is null)
        {
            Browser.Navigate("https://www.youtube.com/");
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
}
