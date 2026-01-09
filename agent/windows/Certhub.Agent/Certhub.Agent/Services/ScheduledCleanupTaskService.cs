namespace Certhub.Agent.Services;

using System.Diagnostics;

public sealed class ScheduledCleanupTaskService
{
    private const string TaskName = "CertHub Cleanup 18h";
    private const string TaskDescription = "Remove temporary CertHub certificates daily at 18:00";
    private const string KeepUntilTaskPrefix = "CertHub KeepUntil";
    private readonly Logger _logger;

    public ScheduledCleanupTaskService(Logger logger)
    {
        _logger = logger;
    }

    public void EnsureDailyCleanupTask(string executablePath)
    {
        try
        {
            if (string.IsNullOrWhiteSpace(executablePath))
            {
                _logger.Warn("Cannot register cleanup task: executable path is empty.");
                return;
            }

            var args = $"/Create /TN \"{TaskName}\" /SC DAILY /ST 18:00 /TR \"\\\"{executablePath}\\\" --cleanup --mode=scheduled\" /RL LIMITED /IT /F";
            RunSchtasks(args, $"Scheduled task ensured: {TaskName}");
        }
        catch (Exception ex)
        {
            _logger.Error("Failed to ensure scheduled cleanup task", ex);
        }
    }

    public void EnsureKeepUntilCleanupTask(DateTimeOffset keepUntilUtc, string executablePath)
    {
        if (string.IsNullOrWhiteSpace(executablePath))
        {
            _logger.Warn("Cannot register keep-until cleanup task: executable path is empty.");
            return;
        }

        var localTime = keepUntilUtc.ToLocalTime();
        var scheduledTime = new DateTimeOffset(
            localTime.Year,
            localTime.Month,
            localTime.Day,
            localTime.Hour,
            localTime.Minute,
            0,
            localTime.Offset);
        if (localTime.Second > 0 || localTime.Millisecond > 0)
        {
            scheduledTime = scheduledTime.AddMinutes(1);
        }

        _logger.Info($"Keep-until requested: {localTime:O}; scheduled at minute boundary: {scheduledTime:O}");

        if (scheduledTime <= DateTimeOffset.Now)
        {
            _logger.Warn($"Keep-until time already passed ({scheduledTime:O}); skipping task creation.");
            return;
        }

        try
        {
            var taskName = $"{KeepUntilTaskPrefix} {scheduledTime:yyyyMMdd-HHmm}";
            var startLocal = scheduledTime.DateTime;
            var endLocal = startLocal.AddMinutes(10);

            var args = $"/Create /TN \"{taskName}\" /SC ONCE /ST {startLocal:HH:mm:ss} /SD {startLocal:dd/MM/yyyy} " +
                       $"/TR \"\\\"{executablePath}\\\" --cleanup --mode=keep_until --task-name \\\"{taskName}\\\"\" " +
                       $"/RL LIMITED /IT /F";

            RunSchtasks(args, $"Created keep-until scheduled cleanup task: {taskName}");
        }
        catch (Exception ex)
        {
            _logger.Error("Failed to ensure keep-until cleanup task.", ex);
        }
    }

    private void RunSchtasks(string args, string successMessage)
    {
        try
        {
            using var process = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = "schtasks.exe",
                    Arguments = args,
                    UseShellExecute = false,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    CreateNoWindow = true
                }
            };

            process.Start();
            var output = process.StandardOutput.ReadToEnd();
            var error = process.StandardError.ReadToEnd();
            process.WaitForExit();

            if (process.ExitCode == 0)
            {
                _logger.Info(successMessage);
            }
            else
            {
                _logger.Error($"schtasks failed with exit code {process.ExitCode}. Error: {error}");
            }
        }
        catch (Exception ex)
        {
            _logger.Error("Failed to execute schtasks.exe", ex);
        }
    }

}

