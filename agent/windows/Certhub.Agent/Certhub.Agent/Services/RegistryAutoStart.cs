using Microsoft.Win32;

namespace Certhub.Agent.Services;

public static class RegistryAutoStart
{
    private const string RunKeyPath = "Software\\Microsoft\\Windows\\CurrentVersion\\Run";
    private const string ValueName = "CertHubAgent";

    public static void Enable()
    {
        using var key = Registry.CurrentUser.OpenSubKey(RunKeyPath, true) ??
                        Registry.CurrentUser.CreateSubKey(RunKeyPath, true);
        if (key is null)
        {
            return;
        }

        var exePath = Environment.ProcessPath ?? Application.ExecutablePath;
        key.SetValue(ValueName, exePath);
    }

    public static void Disable()
    {
        using var key = Registry.CurrentUser.OpenSubKey(RunKeyPath, true);
        key?.DeleteValue(ValueName, false);
    }

    public static bool IsEnabled()
    {
        using var key = Registry.CurrentUser.OpenSubKey(RunKeyPath, false);
        var value = key?.GetValue(ValueName) as string;
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        var exePath = Environment.ProcessPath ?? Application.ExecutablePath;
        return string.Equals(value, exePath, StringComparison.OrdinalIgnoreCase);
    }
}
