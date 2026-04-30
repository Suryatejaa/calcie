namespace CalcieTray.Services;

public sealed class PlayerWindowController : IDisposable
{
    private PlayerWindow? _playerWindow;

    public void ShowPlayer()
    {
        EnsureWindow();
        _playerWindow!.ShowPlayer();
    }

    public void LoadUrl(string url, string title, string subtitle)
    {
        EnsureWindow();
        _playerWindow!.LoadUrl(url, title, subtitle);
    }

    public void ResumePlayer()
    {
        EnsureWindow();
        _playerWindow!.ResumePlayback();
        _playerWindow!.ShowPlayer();
    }

    public void PausePlayer()
    {
        EnsureWindow();
        _playerWindow!.PausePlayback();
    }

    public void SkipNext()
    {
        EnsureWindow();
        _playerWindow!.SkipNext();
        _playerWindow!.ShowPlayer();
    }

    public void PreviousTrack()
    {
        EnsureWindow();
        _playerWindow!.PreviousTrack();
        _playerWindow!.ShowPlayer();
    }

    public void RestartCurrent()
    {
        EnsureWindow();
        _playerWindow!.RestartCurrent();
        _playerWindow!.ShowPlayer();
    }

    private void EnsureWindow()
    {
        if (_playerWindow is not null)
        {
            return;
        }

        _playerWindow = new PlayerWindow();
    }

    public void Dispose()
    {
        if (_playerWindow is null)
        {
            return;
        }

        _playerWindow.AllowExit = true;
        _playerWindow.Close();
        _playerWindow = null;
    }
}
