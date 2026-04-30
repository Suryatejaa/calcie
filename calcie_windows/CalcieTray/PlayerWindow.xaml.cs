using System.ComponentModel;
using Microsoft.Web.WebView2.Core;
using System.Windows;

namespace CalcieTray;

public partial class PlayerWindow : Window
{
    public bool AllowExit { get; set; }
    private string _currentUrl = "https://www.youtube.com/";

    public PlayerWindow()
    {
        InitializeComponent();
        Loaded += async (_, _) => await EnsureBrowserReadyAsync();
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

    public async void LoadUrl(string url, string title, string subtitle)
    {
        Title = title;
        StateText.Text = "Loading";
        SubtitleText.Text = subtitle;
        _currentUrl = string.IsNullOrWhiteSpace(url) ? "https://www.youtube.com/" : url;
        await EnsureBrowserReadyAsync();
        Browser.Source = new Uri(_currentUrl);
        ShowPlayer();
    }

    public async void ResumePlayback()
    {
        await ExecuteScriptAsync(
            """
            (() => {
              const media = document.querySelector('video, audio');
              if (media) {
                media.play();
                return true;
              }
              const selectors = [
                'button[aria-label*="Play"]',
                'button[title*="Play"]',
                'tp-yt-paper-icon-button[aria-label*="Play"]',
                'tp-yt-paper-icon-button[title*="Play"]'
              ];
              for (const selector of selectors) {
                const button = document.querySelector(selector);
                if (button) {
                  button.click();
                  return true;
                }
              }
              return false;
            })();
            """
        );
        StateText.Text = "Playing";
    }

    public async void PausePlayback()
    {
        await ExecuteScriptAsync(
            """
            (() => {
              const media = document.querySelector('video, audio');
              if (media) {
                media.pause();
                return true;
              }
              const selectors = [
                'button[aria-label*="Pause"]',
                'button[title*="Pause"]',
                'tp-yt-paper-icon-button[aria-label*="Pause"]',
                'tp-yt-paper-icon-button[title*="Pause"]'
              ];
              for (const selector of selectors) {
                const button = document.querySelector(selector);
                if (button) {
                  button.click();
                  return true;
                }
              }
              return false;
            })();
            """
        );
        StateText.Text = "Paused";
    }

    public async void SkipNext()
    {
        await ExecuteScriptAsync(
            """
            (() => {
              const selectors = [
                'tp-yt-paper-icon-button[aria-label*="Next"]',
                'button[aria-label*="Next"]',
                'button[title*="Next"]'
              ];
              for (const selector of selectors) {
                const button = document.querySelector(selector);
                if (button) {
                  button.click();
                  return true;
                }
              }
              return false;
            })();
            """
        );
        StateText.Text = "Playing";
    }

    public async void PreviousTrack()
    {
        await ExecuteScriptAsync(
            """
            (() => {
              const selectors = [
                'tp-yt-paper-icon-button[aria-label*="Previous"]',
                'button[aria-label*="Previous"]',
                'button[title*="Previous"]'
              ];
              for (const selector of selectors) {
                const button = document.querySelector(selector);
                if (button) {
                  button.click();
                  return true;
                }
              }
              return false;
            })();
            """
        );
        StateText.Text = "Playing";
    }

    public async void RestartCurrent()
    {
        await ExecuteScriptAsync(
            """
            (() => {
              const media = document.querySelector('video, audio');
              if (!media) {
                return false;
              }
              media.currentTime = 0;
              media.play();
              return true;
            })();
            """
        );
        StateText.Text = "Playing";
    }

    private async Task EnsureBrowserReadyAsync()
    {
        if (Browser.CoreWebView2 is not null)
        {
            return;
        }

        await Browser.EnsureCoreWebView2Async();
        Browser.CoreWebView2.Settings.AreDefaultContextMenusEnabled = true;
        Browser.CoreWebView2.Settings.AreDevToolsEnabled = false;
        Browser.CoreWebView2.Settings.IsStatusBarEnabled = false;
        Browser.CoreWebView2.Settings.IsZoomControlEnabled = false;
        Browser.NavigationStarting += Browser_NavigationStarting;
        Browser.NavigationCompleted += Browser_NavigationCompleted;
    }

    private async Task ExecuteScriptAsync(string script)
    {
        await EnsureBrowserReadyAsync();
        if (Browser.CoreWebView2 is null)
        {
            return;
        }

        try
        {
            await Browser.CoreWebView2.ExecuteScriptAsync(script);
        }
        catch
        {
            // Keep the player resilient even if a page rejects the script.
        }
    }

    private void Reload_Click(object sender, RoutedEventArgs e)
    {
        StateText.Text = "Loading";
        if (Browser.CoreWebView2 is not null)
        {
            Browser.Reload();
            return;
        }

        LoadUrl(_currentUrl, "CALCIE Player", "Reloading inside the CALCIE-owned player surface.");
    }

    private void YouTube_Click(object sender, RoutedEventArgs e)
    {
        LoadUrl("https://www.youtube.com/", "CALCIE Player", "Opening YouTube in the CALCIE-owned player surface.");
    }

    private void YouTubeMusic_Click(object sender, RoutedEventArgs e)
    {
        LoadUrl("https://music.youtube.com/", "CALCIE Player", "Opening YouTube Music in the CALCIE-owned player surface.");
    }

    private void Browser_NavigationStarting(object? sender, CoreWebView2NavigationStartingEventArgs e)
    {
        StateText.Text = "Loading";
    }

    private void Browser_NavigationCompleted(object? sender, CoreWebView2NavigationCompletedEventArgs e)
    {
        StateText.Text = e.IsSuccess ? "Ready" : "Error";
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
