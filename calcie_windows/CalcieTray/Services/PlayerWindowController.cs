namespace CalcieTray.Services;

public sealed class PlayerWindowController : IDisposable
{
    private PlayerWindow? _playerWindow;

    public void ShowPlayer()
    {
        EnsureWindow();
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
