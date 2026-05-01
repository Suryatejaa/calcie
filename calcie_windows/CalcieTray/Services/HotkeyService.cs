using System.Runtime.InteropServices;
using System.Windows.Interop;

namespace CalcieTray.Services;

public sealed class HotkeyService : IDisposable
{
    private const int HotkeyIdTogglePrimary = 0xC411;
    private const int HotkeyIdToggleSecondary = 0xC412;
    private const int WmHotkey = 0x0312;
    private const int WhKeyboardLl = 13;
    private const int WmKeyDown = 0x0100;
    private const int WmKeyUp = 0x0101;
    private const int WmSysKeyDown = 0x0104;
    private const int WmSysKeyUp = 0x0105;
    private const uint ModNone = 0x0000;
    private const uint ModControl = 0x0002;
    private const uint ModShift = 0x0004;
    private const uint VkSpace = 0x20;
    private const uint VkRControl = 0xA3;
    private const uint VkRMenu = 0xA5;
    private const uint VkF8 = 0x77;

    private HwndSource? _source;
    private bool _registered;
    private IntPtr _keyboardHook = IntPtr.Zero;
    private HookProc? _keyboardProc;
    private bool _rightControlDown;
    private bool _rightAltDown;

    public event EventHandler? HotkeyPressed;
    public event EventHandler? PressStarted;
    public event EventHandler? PressEnded;

    public string Description => "Hold Right Ctrl or Right Alt";
    public string FallbackDescription => "F8 or Ctrl+Shift+Space";

    public bool Register()
    {
        if (_registered || _keyboardHook != IntPtr.Zero)
        {
            return true;
        }

        var parameters = new HwndSourceParameters("CalcieTrayHotkeySink")
        {
            Width = 0,
            Height = 0,
            WindowStyle = 0x800000
        };

        _source = new HwndSource(parameters);
        _source.AddHook(WndProc);

        var primaryRegistered = RegisterHotKey(_source.Handle, HotkeyIdTogglePrimary, ModControl | ModShift, VkSpace);
        var secondaryRegistered = RegisterHotKey(_source.Handle, HotkeyIdToggleSecondary, ModNone, VkF8);
        _registered = primaryRegistered || secondaryRegistered;

        _keyboardProc = KeyboardProc;
        _keyboardHook = SetWindowsHookEx(WhKeyboardLl, _keyboardProc, GetModuleHandle(null), 0);

        return _registered || _keyboardHook != IntPtr.Zero;
    }

    public void Unregister()
    {
        if (_keyboardHook != IntPtr.Zero)
        {
            UnhookWindowsHookEx(_keyboardHook);
            _keyboardHook = IntPtr.Zero;
            _keyboardProc = null;
            _rightControlDown = false;
            _rightAltDown = false;
        }

        if (_source is not null)
        {
            if (_registered)
            {
                UnregisterHotKey(_source.Handle, HotkeyIdTogglePrimary);
                UnregisterHotKey(_source.Handle, HotkeyIdToggleSecondary);
            }

            _source.RemoveHook(WndProc);
            _source.Dispose();
        }

        _source = null;
        _registered = false;
    }

    private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        if (msg == WmHotkey && (wParam.ToInt32() == HotkeyIdTogglePrimary || wParam.ToInt32() == HotkeyIdToggleSecondary))
        {
            handled = true;
            HotkeyPressed?.Invoke(this, EventArgs.Empty);
        }

        return IntPtr.Zero;
    }

    private IntPtr KeyboardProc(int nCode, IntPtr wParam, IntPtr lParam)
    {
        if (nCode >= 0)
        {
            var message = wParam.ToInt32();
            var hookStruct = Marshal.PtrToStructure<KbdLlHookStruct>(lParam);
            if (hookStruct.vkCode == VkRControl)
            {
                if ((message == WmKeyDown || message == WmSysKeyDown) && !_rightControlDown)
                {
                    _rightControlDown = true;
                    PressStarted?.Invoke(this, EventArgs.Empty);
                }
                else if ((message == WmKeyUp || message == WmSysKeyUp) && _rightControlDown)
                {
                    _rightControlDown = false;
                    PressEnded?.Invoke(this, EventArgs.Empty);
                }
            }
            else if (hookStruct.vkCode == VkRMenu)
            {
                if ((message == WmKeyDown || message == WmSysKeyDown) && !_rightAltDown)
                {
                    _rightAltDown = true;
                    PressStarted?.Invoke(this, EventArgs.Empty);
                }
                else if ((message == WmKeyUp || message == WmSysKeyUp) && _rightAltDown)
                {
                    _rightAltDown = false;
                    PressEnded?.Invoke(this, EventArgs.Empty);
                }
            }
        }

        return CallNextHookEx(_keyboardHook, nCode, wParam, lParam);
    }

    public void Dispose()
    {
        Unregister();
    }

    private delegate IntPtr HookProc(int nCode, IntPtr wParam, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential)]
    private struct KbdLlHookStruct
    {
        public uint vkCode;
        public uint scanCode;
        public uint flags;
        public uint time;
        public IntPtr dwExtraInfo;
    }

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool UnregisterHotKey(IntPtr hWnd, int id);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr SetWindowsHookEx(int idHook, HookProc lpfn, IntPtr hMod, uint dwThreadId);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool UnhookWindowsHookEx(IntPtr hhk);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr CallNextHookEx(IntPtr hhk, int nCode, IntPtr wParam, IntPtr lParam);

    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern IntPtr GetModuleHandle(string? lpModuleName);
}
