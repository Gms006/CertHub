namespace Certhub.Agent.Services;

public sealed class Logger
{
    private readonly string _logFilePath;
    private readonly object _lock = new();

    public Logger()
    {
        var baseDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "CertHubAgent");
        var logsDir = Path.Combine(baseDir, "logs");
        Directory.CreateDirectory(logsDir);
        _logFilePath = Path.Combine(logsDir, "agent.log");
    }

    public void Info(string message) => Write("INFO", message);
    public void Warn(string message) => Write("WARN", message);
    public void Error(string message, Exception? ex = null)
    {
        var detail = ex is null ? message : $"{message} | {ex.GetType().Name}: {ex.Message}";
        Write("ERROR", detail);
    }

    private void Write(string level, string message)
    {
        var line = $"[{DateTimeOffset.Now:O}] {level} {message}";
        lock (_lock)
        {
            File.AppendAllText(_logFilePath, line + Environment.NewLine);
        }
    }
}
