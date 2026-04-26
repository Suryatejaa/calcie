using System.Diagnostics;
using System.IO;

namespace CalcieTray.Services;

public sealed class RuntimeLauncher : IDisposable
{
    private readonly string _projectRoot;
    private Process? _runtimeProcess;
    private bool _ownsRuntimeProcess;
    private DateTimeOffset _lastLaunchAttempt = DateTimeOffset.MinValue;

    public RuntimeLauncher()
    {
        _projectRoot = ResolveProjectRoot();
    }

    public string ProjectRoot => _projectRoot;

    public bool CanLaunch => Directory.Exists(_projectRoot);

    public bool IsRunning => _runtimeProcess is { HasExited: false };

    public string EnsureRunning()
    {
        if (IsRunning)
        {
            return $"Started local CALCIE runtime (pid {_runtimeProcess!.Id}).";
        }

        if (!CanLaunch)
        {
            return $"Runtime root not found. Set CALCIE_PROJECT_ROOT before launching the Windows shell.";
        }

        var now = DateTimeOffset.UtcNow;
        if ((now - _lastLaunchAttempt) < TimeSpan.FromSeconds(12))
        {
            return "Waiting before the next runtime launch attempt.";
        }

        _lastLaunchAttempt = now;

        foreach (var candidate in LaunchCandidates())
        {
            try
            {
                var process = new Process
                {
                    StartInfo = new ProcessStartInfo
                    {
                        FileName = candidate.FileName,
                        Arguments = candidate.Arguments,
                        WorkingDirectory = _projectRoot,
                        UseShellExecute = false,
                        CreateNoWindow = true,
                        RedirectStandardOutput = false,
                        RedirectStandardError = false
                    },
                    EnableRaisingEvents = true
                };

                process.StartInfo.Environment["CALCIE_PROJECT_ROOT"] = _projectRoot;
                process.Start();
                _runtimeProcess = process;
                _ownsRuntimeProcess = true;
                return $"Started local CALCIE runtime via `{candidate.Display}`.";
            }
            catch
            {
                // Try the next candidate.
            }
        }

        return "Failed to launch local CALCIE runtime. Make sure Python is installed and CALCIE_PROJECT_ROOT points to the Jarvis repo.";
    }

    private static IEnumerable<(string FileName, string Arguments, string Display)> LaunchCandidates()
    {
        yield return ("py", "-3 -m calcie_local_api.server", "py -3 -m calcie_local_api.server");
        yield return ("python", "-m calcie_local_api.server", "python -m calcie_local_api.server");
        yield return ("python3", "-m calcie_local_api.server", "python3 -m calcie_local_api.server");
    }

    private static string ResolveProjectRoot()
    {
        var fromEnv = Environment.GetEnvironmentVariable("CALCIE_PROJECT_ROOT");
        if (!string.IsNullOrWhiteSpace(fromEnv))
        {
            return Path.GetFullPath(fromEnv);
        }

        var current = AppContext.BaseDirectory;
        var probe = new DirectoryInfo(current);
        while (probe is not null)
        {
            if (File.Exists(Path.Combine(probe.FullName, "calcie.py")))
            {
                return probe.FullName;
            }

            probe = probe.Parent;
        }

        return current;
    }

    public void Dispose()
    {
        if (_runtimeProcess is null)
        {
            return;
        }

        try
        {
            if (!_runtimeProcess.HasExited)
            {
                if (_ownsRuntimeProcess)
                {
                    _runtimeProcess.Kill(entireProcessTree: true);
                    _runtimeProcess.WaitForExit(3000);
                }

                _runtimeProcess.Dispose();
            }
        }
        catch
        {
        }
        finally
        {
            _runtimeProcess = null;
            _ownsRuntimeProcess = false;
        }
    }
}
