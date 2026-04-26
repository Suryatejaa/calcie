using System.Windows;
using System.Windows.Media.Imaging;
using CalcieTray.ViewModels;

namespace CalcieTray;

public partial class SettingsWindow : Window
{
    public SettingsWindow(ShellViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
        if (TryLoadLogo() is { } logo)
        {
            Icon = logo;
        }
    }

    private static BitmapFrame? TryLoadLogo()
    {
        try
        {
            return BitmapFrame.Create(new Uri("pack://application:,,,/Assets/calcie-logo.png", UriKind.Absolute));
        }
        catch
        {
            return null;
        }
    }
}
