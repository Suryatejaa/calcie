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
